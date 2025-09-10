from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from schemas.response_schema import APIResponse

app = FastAPI(root_path="/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            status_code=exc.status_code,
            data=None,
            detail=exc.detail,
        ).dict()
    )
@app.get("/")
def read_root():
    return {"message": "Hello from FasterAPI!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# --- auto-routes-start ---
from api.v1.game import router as v1_game_router
from api.v1.leaderboard import router as v1_leaderboard_router
from api.v1.match import router as v1_match_router
from api.v1.player import router as v1_player_router
from api.v1.scores import router as v1_scores_router
from api.v1.secret import router as v1_secret_router
from api.v1.user import router as v1_user_router

app.include_router(v1_game_router)
app.include_router(v1_leaderboard_router)
app.include_router(v1_match_router)
app.include_router(v1_player_router)
app.include_router(v1_scores_router)
app.include_router(v1_secret_router)
app.include_router(v1_user_router)
# --- auto-routes-end ---