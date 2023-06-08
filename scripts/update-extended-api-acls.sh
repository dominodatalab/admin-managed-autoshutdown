#!/bin/bash
set -e
echo "USAGE: ./update-api-admin.sh"
platform_namespace="${platform_namespace:-domino-platform}"
admins_secret="extended-api-acls"

#kubectl delete secret ${admins_secret} -n ${platform_namespace}

# create the secrets for admins admin user list
kubectl create secret generic ${admins_secret} \
        --from-file=${admins_secret}=./${admins_secret}.json \
        --dry-run=client -o yaml |
    kubectl -n ${platform_namespace} apply -f -