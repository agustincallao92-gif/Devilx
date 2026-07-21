"""
XytoUniversalSearch - FastAPI Backend
Uses the Apify Actor: misceres/sherlock (400+ social networks)

Setup on Termux:
  pkg install python
  pip install fastapi uvicorn httpx
  python server.py
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx
import os

# ─────────────────────────────────────────────
#  🔑  TOKEN SETUP (two options):
#
#  LOCAL (Termux):
#    Edit this line directly:
#    APIFY_TOKEN = "apify_api_xxxxxxxxxxxx"
#
#  HOSTED (Render):
#    Leave this as-is — set APIFY_TOKEN in
#    Render dashboard → Environment Variables
# ─────────────────────────────────────────────
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "YOUR_APIFY_TOKEN_HERE")

APIFY_BASE = "https://api.apify.com/v2/acts/misceres~sherlock"

app = FastAPI(title="XytoUniversalSearch API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return FileResponse("index.html")


class SearchRequest(BaseModel):
    username: str


@app.get("/api/status")
async def status():
    return {
        "status": "online",
        "provider": "Apify — misceres/sherlock",
        "token_set": APIFY_TOKEN != "YOUR_APIFY_TOKEN_HERE"
    }


@app.post("/api/search")
async def search_username(payload: SearchRequest):
    """
    Calls the Apify Sherlock Actor synchronously and returns
    the full dataset of results (found & not-found platforms).
    """
    if APIFY_TOKEN == "YOUR_APIFY_TOKEN_HERE":
        raise HTTPException(
            status_code=503,
            detail="Apify token not set. Open server.py and paste your token."
        )

    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty.")

    # Apify Sherlock input: list of usernames
    body = {"usernames": [username]}

    try:
        # run-sync-get-dataset-items waits for the run to finish
        # and returns the dataset array directly — can take ~30–90s
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{APIFY_BASE}/run-sync-get-dataset-items?token={APIFY_TOKEN}",
                json=body,
                headers={"Content-Type": "application/json"},
            )

        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid Apify token.")
        if resp.status_code == 429:
            raise HTTPException(status_code=429, detail="Apify rate limit hit. Try again later.")
        if resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Apify error: {resp.text[:300]}"
            )

        raw = resp.json()   # list of result objects from the dataset

        # Normalise into a consistent shape for the frontend:
        # Each item from misceres/sherlock looks like:
        # { "username": "...", "site": "GitHub", "url": "...", "status": "found" }
        results = []
        for item in raw:
            results.append({
                "platform": item.get("site") or item.get("siteName") or item.get("platform", "Unknown"),
                "url":      item.get("url") or item.get("link") or "",
                "found":    str(item.get("status", "")).lower() == "found"
                            or item.get("found") is True,
            })

        found_count = sum(1 for r in results if r["found"])
        return {
            "username": username,
            "total":    len(results),
            "found":    found_count,
            "results":  results,
        }

    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot reach Apify. Check your internet.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Apify search timed out (120s). Try again.")


if __name__ == "__main__":
    import uvicorn
    print("\n🔍 XytoUniversalSearch — Apify Edition")
    print("   Open http://localhost:8000 in your browser\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
