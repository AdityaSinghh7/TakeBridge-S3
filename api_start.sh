source ../TakeBridge-S3/.venv/bin/activate
NODE_EXTRA_CA_CERTS="$(mkcert -CAROOT)/rootCA.pem" NODE_OPTIONS="--use-openssl-ca --use-system-ca" uvicorn server.api.server:app --host 0.0.0.0 --port 8000 --ssl-keyfile ./localhost+1-key.pem --ssl-certfile ./localhost+1.pem
