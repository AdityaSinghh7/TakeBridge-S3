web: uvicorn server.api.server:app --host 0.0.0.0 --port 8000 --ssl-keyfile ./localhost+1-key.pem --ssl-certfile ./localhost+1.pem
runtime: uvicorn runtime.api.server:app --host 0.0.0.0 --port 8001
worker: python -m worker.run_worker
