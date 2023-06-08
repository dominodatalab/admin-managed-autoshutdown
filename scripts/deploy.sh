#!/bin/bash
set -e
echo "USAGE: ./deploy.sh VERSION"
readonly_support_admin=""${readonly_support_admin:-true}""
domsed_extendedapi_image="${domsed_extendedapi_image:-quay.io/domino/domino-extendedapi}"
platform_namespace="${platform_namespace:-domino-platform}"
name="operator"
deployment_name="domino-extendedapi"
admins_secret="extended-api-acls"

VERSION=$1

if [ -z "$VERSION" ]
then
      echo "Please specify a version."
      exit 1
fi

secret="${deployment_name}-certs"
service="${deployment_name}-svc"


# create the secrets for admins admin user list
kubectl create secret generic ${admins_secret} \
        --from-file=${admins_secret}=./${admins_secret}.json \
        --dry-run=client -o yaml |
    kubectl -n ${platform_namespace} apply -f -

echo "Creating Deployment"
cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${deployment_name}
  labels:
    app: ${deployment_name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${deployment_name}
  template:
    metadata:
      labels:
        app: ${deployment_name}
        nucleus-client: "true"
        security.istio.io/tlsMode: "istio"
        mongodb-replicaset-client: "true"
    spec:
      nodeSelector:
        dominodatalab.com/node-pool: platform
      containers:
      - name: ${deployment_name}
        securityContext:
          runAsUser: 1000
          runAsGroup: 1000
          allowPrivilegeEscalation: false
          capabilities:
            drop:
              - all
        image: ${domsed_extendedapi_image}:${VERSION}
        ports:
        - containerPort: 5000
        livenessProbe:
          httpGet:
            path: /healthz
            port: 5000
            scheme: HTTP
          initialDelaySeconds: 20
          failureThreshold: 2
          timeoutSeconds: 5
        readinessProbe:
          httpGet:
            path: /healthz
            port: 5000
            scheme: HTTP
          initialDelaySeconds: 20
          failureThreshold: 2
          timeoutSeconds: 5
        imagePullPolicy: Always
        env:
        - name: PLATFORM_NAMESPACE
          value: ${platform_namespace}
        - name: MONGO_PASSWORD
          valueFrom:
            secretKeyRef:
              key: password
              name: mongodb-replicaset-admin
        volumeMounts:
          - name: admins
            mountPath: /admins
            readOnly: true
      volumes:
        - name: admins
          secret:
            secretName: ${admins_secret}
EOF

echo "Creating Service"
cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: v1
kind: Service
metadata:
  labels:
    app: ${deployment_name}
  name: ${service}
  namespace: ${platform_namespace}
spec:
  ports:
  - name: http
    port: 80
    targetPort: 5000
  selector:
    app: ${deployment_name}
  sessionAffinity: None
  type: ClusterIP
EOF

# Wait for the app to actually be up before starting the webhook.
let tries=1
availreps=""
while [[ ${tries} -lt 10 && "${availreps}" != "1" ]]; do
  echo "Checking deployment, try $tries"
  kubectl get deployment -n ${platform_namespace} ${deployment_name}
  availreps=$(kubectl get deployment -n ${platform_namespace} ${name}-webhook -o jsonpath='{.status.availableReplicas}')
  let tries+=1
  sleep 10
done

if [[ ${availreps} != "1" ]]; then
  echo "Deployment never became available, exiting."
  exit 1
fi
echo "Creating Network Policy"

cat <<EOF | kubectl create -n ${platform_namespace} -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ${deployment_name}
spec:
  ingress:
  - from:
    - ipBlock:
        cidr: 0.0.0.0/0
    ports:
    - port: 5000
      protocol: TCP
  podSelector:
    matchLabels:
      app: ${deployment_name}
  policyTypes:
  - Ingress
EOF



