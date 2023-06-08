# Domino Extended API (Field Extensions)

This library enables adding new API endpoints to support customer requirements 


### Who is permitted to manage mutation

In the root folder there is a file `extended-api-acls.json`
```json
{
  "users":["fake-admin"]
}
```

The following users can manage Mutation using their Domino API Key:

1. Domino Administrators
2. Users listed in the `extended-api-acls.json`

Currently these users can call endpoints. In the future it is possible to allow users access to specific endpoints   
   

###Installation

From the root folder of this project run the following commands:

1. First publish the image
```
tag="${tag:-latest}"
operator_image="${operator_image:-quay.io/domino/domino-extendedapi}"
docker build -f ./Dockerfile -t ${operator_image}:${tag} .
docker push ${operator_image}:${tag}
```

2. Update the file `extended-api-acls.json` based on your access requirements. Default file below 
   only allows Domino Administrators to update mutations 
```json
{
  "users":[""]
}
```
3. Install the service
```shell
./scripts/deploy.sh $image_tag
```
4. Optionally destroy the webserver before deploying it
```shell
./scripts/destroy.sh
```
###Updating permissions after install

If you want to update permissions post install, update the file `domsedadmins.json` and run the script
```shell
./scripts/update-extended-api-acls.sh
```

###Using the API

The API provides the following endpoints:

## v4-extended/autoshutdownwksrules

The full endpoint inside the Domino workspace is (assuming `domino-platform` as the platform namespace)
```shell
http://domino-extendedapi-svc.domino-platform/v4-extended/autoshutdownwksrules
```

Type : POST

Headers and Body:
```
--header 'X-Domino-Api-Key: ADD YOUR API KEY HERE ' \
--header 'Content-Type: application/json' \
--data-raw '{
    "users": {
        "wadkars": 3600,
        "integration-test":  21600
    },
    "override_to_default" : false
}'
```

For each user you want to override the default value update the `users`
attribute above as:
`{domino-user-name}` : {auto_shutdown_duration_in_seconds}

The default auto-shutdown-duration is obtained from the central config parameter:
```shell
com.cerebro.domino.workspaceAutoShutdown.globalDefaultLifetimeInSeconds
```
The `override_to_default` attribute is used to determine if all users (not specificied)
in the `users` attribute tag as also update to have their default autoshutdown duration
set to default.

if `override_to_default` is set to `true` every user except the users mentioned in the 
`users` attribute will be configured for the default value of autoshutdown

The value of `com.cerebro.domino.workspaceAutoShutdown.globalDefaultLifetimeInSeconds`
is expected to be lower than `com.cerebro.domino.workspaceAutoShutdown.globalMaximumLifetimeInSeconds`

Likewise for the values provided for each user in the `users` attribute

If not, the auto shutdown duration is capped at the value of `com.cerebro.domino.workspaceAutoShutdown.globalMaximumLifetimeInSeconds`


An example Python client is provided in the file `client/extended_api_client.py`.
Copy its content to a workbook and try it out.