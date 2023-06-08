#!/bin/bash
set -x
echo "USAGE: ./destroy.sh"

name="operator"
platform_namespace="${platform_namespace:-domino-platform}"
deployment_name="domino-extendedapi"
admins_secret="extended-api-acls"


service="${deployment_name}-svc"


kubectl delete secret ${admins_secret} -n ${platform_namespace}
kubectl delete deployment -n ${platform_namespace} "${deployment_name}"
kubectl delete networkpolicy -n ${platform_namespace} "${deployment_name}"
kubectl delete svc -n ${platform_namespace} ${service}
