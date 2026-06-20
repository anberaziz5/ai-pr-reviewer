from fastapi import FastAPI, Request, HTTPException
import google.generativeai as genai
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Configure APIs
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

@app.post("/webhook")
async def github_webhook(request: Request):
    """Listens for GitHub Pull Request events."""
    payload = await request.json()
    
    # We only care about PRs being opened or updated
    if payload.get("action") not in ["opened", "synchronize"]:
        return {"status": "Ignored: Not a PR open or sync event"}
        
    if "pull_request" not in payload:
        return {"status": "Ignored: No PR data"}

    # Extract vital PR information
    pr_number = payload["pull_request"]["number"]
    repo_full_name = payload["repository"]["full_name"]
    diff_url = payload["pull_request"]["diff_url"]
    
    # 1. Fetch the Code Diff
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff"
    }
    
    diff_response = requests.get(diff_url, headers=headers)
    if diff_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Could not fetch PR diff")
        
    diff_text = diff_response.text
    
    # Check if diff is too large or empty
    if not diff_text or len(diff_text) > 20000:
        return {"status": "Ignored: Diff too large or empty"}

    # 2. Prompt Gemini for Code Review
    prompt = f"""
    You are an expert senior software engineer conducting a code review.
    Analyze the following GitHub Pull Request diff.
    
    Focus on:
    1. Bugs or logic errors.
    2. Security vulnerabilities.
    3. Performance improvements.
    4. Code readability and best practices.
    
    Do NOT comment on minor formatting unless it's egregious.
    Format your response in Markdown, using clear headings and bullet points.
    Keep it concise, professional, and actionable.
    
    Code Diff:
    ```diff
    {diff_text}
    ```
    """
    
    try:
        ai_response = model.generate_content(prompt)
        review_comment = ai_response.text
    except Exception as e:
        print(f"AI Error: {e}")
        return {"status": "Error generating review"}

    # 3. Post the Review back to GitHub
    comment_url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments"
    comment_payload = {
        "body": f"🤖 **AI Code Review:**\n\n{review_comment}"
    }
    
    post_response = requests.post(comment_url, headers=headers, json=comment_payload)
    
    if post_response.status_code == 201:
         return {"status": "Success: Review posted!"}
    else:
         raise HTTPException(status_code=500, detail="Failed to post comment to GitHub")

@app.get("/")
def health_check():
    return {"status": "AI PR Reviewer is running!"}