from typing import Dict

from flask import Flask, request, Response  # type: ignore
import logging
import json
from urllib.parse import quote_plus
from pymongo import MongoClient  # type: ignore
import os
import sys
import requests

DEFAULT_PLATFORM_NAMESPACE = "domino-platform"
WHO_AM_I_ENDPOINT = "v4/auth/principal"
DOMINO_NUCLEUS_URI = "http://nucleus-frontend.domino-platform:80"
ADMINS_RELATIVE_FILE_PATH = "admins/extended-api-acls"
ADMINS_FILE_PATH = ""

ENABLE_WKS_AUTO_SHUTDOWN = "enableWorkspaceAutoShutdown"
MAX_WKS_LIFETIME = "maximumWorkspaceLifetimeInSeconds"
ENABLE_SESSION_NOTIFICATIONS = "enableSessionNotifications"
SESSION_NOTIFICATION_PERIOD = "sessionNotificationPeriod"
USER_ID = "userId"

logger = logging.getLogger("domino-extended-api")
app = Flask(__name__)


def get_api_acls():
    with open(ADMINS_FILE_PATH, "r") as f:
        admin_rules: Dict = json.load(f)
    return admin_rules


def create_database_connection():
    if os.environ.get("MONGO_PASSWORD") is None:
        return []

    platform_namespace = os.environ.get(
        "PLATFORM_NAMESPACE", DEFAULT_PLATFORM_NAMESPACE
    )
    host = os.environ.get(
        "MONGO_HOST",
        f"mongodb-replicaset.{platform_namespace}.svc.cluster.local:27017",
    )
    username = quote_plus(os.environ.get("MONGO_USERNAME", "admin"))
    password = quote_plus(os.environ["MONGO_PASSWORD"])
    db_name = quote_plus(os.environ.get("MONGO_DB_NAME", "domino"))
    if username == "admin":
        path = ""
    else:
        path = "/{}".format(db_name)
    mongo_uri = "mongodb://{}:{}@{}{}".format(username, password, host, path)
    return MongoClient(mongo_uri)[db_name]


def is_user_authorized(api_key: str):
    acls: Dict = get_api_acls()
    url: str = os.path.join(DOMINO_NUCLEUS_URI, WHO_AM_I_ENDPOINT)
    ret: Dict = requests.get(url, headers={"X-Domino-Api-Key": api_key})
    if ret.status_code == 200:
        user: str = ret.json()
        user_name: str = user["canonicalName"]
        is_admin: bool = user["isAdmin"]
        if is_admin:  # Admins can update mutations
            logger.warning("Allowed because is Admin")
            return True
        elif user_name in acls["users"]:
            logger.warning("Allowed because is in list of admins")
            return True
        else:
            return False
    else:
        raise Exception(str(ret.status_code) + " - Error getting user status")


def get_central_config_parameters(client: MongoClient):
    config_collection = client["config"]

    wks_auto_shutdown_enabled = False
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workspaceAutoShutdown.isEnabled",
        }
    )
    if val:
        wks_auto_shutdown_enabled = bool(val["value"])

    global_max_lifetime = 0
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workspaceAutoShutdown.globalMaximumLifetimeInSeconds",
        }
    )
    if val:
        global_max_lifetime = int(val["value"])

    global_default_lifetime = 0
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workspaceAutoShutdown.globalDefaultLifetimeInSeconds",
        }
    )
    if val:
        global_default_lifetime = int(val["value"])

    wks_notification_enabled = False
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workloadNotifications.isEnabled",
        }
    )
    if val:
        wks_notification_enabled = bool(val["value"])

    wks_notification_duration = 0
    val = config_collection.find_one(
        {
            "namespace": "common",
            "key": "com.cerebro.domino.workloadNotifications.longRunningWorkloadDefinitionInSeconds",
        }
    )
    if val:
        wks_notification_duration = int(val["value"])
    return (
        wks_auto_shutdown_enabled,
        global_max_lifetime,
        global_default_lifetime,
        wks_notification_enabled,
        wks_notification_duration,
    )


"""
1. Get all info on domino autoshutdown from central config
2. Get default val. If default val not present, use max value
3. Get all users
4. Apply default to all user, except for the exception user
5. Input docs is list of users with their timeout.
6. If exception timeout higher than max, override with max
"""


@app.route("/v4-extended/autoshutdownwksrules", methods=["POST"])
def apply_autoshutdown_rules() -> object:
    try:
        if not is_user_authorized(request.headers["X-Domino-Api-Key"]):
            return Response(
                "Unauthorized - Must be Domino Admin or one of the allowed users",
                403,
            )
        logger.warning("Creating Mongo Connection")
        mongo_client = create_database_connection()
        (
            wks_auto_shutdown_enabled,
            global_max_lifetime,
            global_default_lifetime,
            wks_notification_enabled,
            wks_notification_duration,
        ) = get_central_config_parameters(mongo_client)
        logger.warning("Collected auto-shutdown values from central config")
        if not wks_auto_shutdown_enabled:
            return {
                "msg": "com.cerebro.domino.workloadNotifications.isEnabled is False. No changes made"
            }
        elif global_default_lifetime == 0:
            return {
                "msg": "com.cerebro.domino.workloadNotifications.defaultPeriodInSeconds not set. No changes made"
            }
        elif global_default_lifetime > global_max_lifetime:
            return {
                "msg": "com.cerebro.domino.workspaceAutoShutdown.globalDefaultLifetimeInSeconds is greater than "
                "com.cerebro.domino.workspaceAutoShutdown.globalMaximumLifetimeInSeconds. "
                "No changes made"
            }
        else:
            logger.warning("Start updating")
            # read payload
            user_pref_coll = mongo_client["userPreferences"]
            payload = request.json
            domino_users = payload["users"]

            result = mongo_client["users"].aggregate(
                [
                    {
                        "$lookup": {
                            "from": "userPreferences",
                            "localField": "_id",
                            "foreignField": "userId",
                            "as": "joinedResult",
                        }
                    }
                ]
            )

            for r in result:
                user_id = r["loginId"]["id"]
                user_preference = {}
                if user_id in domino_users:
                    wks_lifetime = int(domino_users[user_id])
                    logger.warning(
                        f"Override user {user_id} to autoshutdown in {wks_lifetime} seconds"
                    )
                elif payload["override_to_default"]:
                    wks_lifetime = global_default_lifetime
                    logger.warning(
                        f"Override user {user_id} to default autoshutdown in {wks_lifetime} seconds"
                    )
                else:
                    logger.warning(f"Do not override user {user_id}")

                if len(r["joinedResult"]) == 0:
                    user_preference["notifyAboutCollaboratorAdditions"] = True

                user_preference["userId"] = r["_id"]
                user_preference[ENABLE_WKS_AUTO_SHUTDOWN] = wks_auto_shutdown_enabled
                if wks_lifetime > 0:
                    user_preference[MAX_WKS_LIFETIME] = wks_lifetime
                else:
                    user_preference.pop(MAX_WKS_LIFETIME,-1)

                if wks_notification_enabled:
                    user_preference[
                        ENABLE_SESSION_NOTIFICATIONS
                    ] = wks_notification_enabled
                    user_preference[
                        SESSION_NOTIFICATION_PERIOD
                    ] = wks_notification_duration
                query = {"userId": r["_id"]}
                id = r["_id"]
                if wks_lifetime<0:
                    logger.warning(f"About to delete entry for user {id}")
                    result = user_pref_coll.delete_one({"userId": r["_id"]})
                    logger.warning(f"Deleted entry for user {id} - {result.deleted_count}")
                user_pref_coll.update_one(query, {"$set": user_preference}, upsert=True)
                logger.warning(f"Upserted entry for user {id}")
                print(user_preference)
            return {"msg": "Workspace Shutdown Durations Updated"}
    except Exception as e:
        logger.exception(e)
        return Response(
            str(e),
            500,
        )


@app.route("/healthz")
def alive():
    return "{'status': 'Healthy'}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        DOMINO_NUCLEUS_URI: str = sys.argv[1]
        root_folder: str = sys.argv[2]
    else:
        root_folder = "/"

    ADMINS_FILE_PATH = os.path.join(root_folder, ADMINS_RELATIVE_FILE_PATH)

    lvl: str = logging.getLevelName(os.environ.get("LOG_LEVEL", "DEBUG"))
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    log = logging.getLogger("werkzeug")

    debug: bool = os.environ.get("FLASK_ENV") == "development"
    logger.warning(get_api_acls())

    app.run(
        host=os.environ.get("FLASK_HOST", "0.0.0.0"),
        port=5000,
        debug=debug,
    )
