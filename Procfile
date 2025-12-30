web: uvicorn server.api.server:app --host 0.0.0.0 --port 8000 --reload --ssl-keyfile ./localhost+1-key.pem --ssl-certfile ./localhost+1.pem
worker: python -m worker.run_worker