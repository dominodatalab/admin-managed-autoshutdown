tag="${tag:-latest}"
operator_image="${operator_image:-quay.io/domino/domino-extendedapi}"
docker build -f ./Dockerfile -t ${operator_image}:${tag} .
docker push ${operator_image}:${tag}