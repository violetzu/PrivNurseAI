# /bin/bash

docker build -t import -f Dockerfile.excel2db .

docker run --rm \
        -v ../privnurse_gemma3n/backend/models.py:/app/models.py \
        --network privnurseai_default \
        import