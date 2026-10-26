from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import db, auth, api

db.init()

app = FastAPI(title="backend", lifespan=db.lifespan)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["ani-cli.com"],
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.include_router(auth.router)
app.include_router(api.router)