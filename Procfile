web: uvicorn server.api.server:app --host 0.0.0.0 --port 8000 --reload  --ssl-keyfile ./certs/localhost-key.pem --ssl-certfile ./certs/localhost.pem
worker: python -m worker.run_worker
