from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
import subprocess
import tempfile
import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("musescore-api")

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Immensa Gratia MuseScore Service")

# Allow requests from all origins (CORS) so the browser frontend can upload scores and download PDFs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
        <head>
            <title>Immensa Gratia MusicXML Converter</title>
            <style>
                body { font-family: sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; line-height: 1.6; }
                h1 { color: #c6a87c; }
                .card { border: 1px solid #ddd; padding: 20px; border-radius: 8px; background: #fafafa; }
                button { background: #c6a87c; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; }
                button:hover { background: #b09366; }
            </style>
        </head>
        <body>
            <h1>Immensa Gratia Sheet Music Converter</h1>
            <p>This serverless service processes MusicXML scores using MuseScore 3.</p>
            <div class="card">
                <h3>Test the API</h3>
                <form action="/convert" method="post" enctype="multipart/form-data">
                    <label>Select a MusicXML file (.xml or .musicxml):</label><br><br>
                    <input type="file" name="file" required><br><br>
                    <label>Convert to:</label><br>
                    <select name="format">
                        <option value="pdf">PDF (Printable sheet music)</option>
                        <option value="mp3">MP3 (Synthesized audio)</option>
                        <option value="mid">MIDI (Synthesizer tracks)</option>
                    </select><br><br>
                    <button type="submit">Convert</button>
                </form>
            </div>
        </body>
    </html>
    """

@app.post("/convert")
async def convert_score(
    file: UploadFile = File(...),
    format: str = Form("pdf")
):
    format = format.lower().strip()
    if format not in ["pdf", "mp3", "mid", "wav"]:
        raise HTTPException(status_code=400, detail="Invalid format. Supported: pdf, mp3, mid, wav")

    # 1. Create a secure temporary directory for processing
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Save uploaded file
        input_filename = "score.musicxml"
        input_file_path = tmp_path / input_filename
        
        with open(input_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        output_filename = f"output.{format}"
        output_file_path = tmp_path / output_filename
        
        logger.info(f"Received file: {file.filename}. Converting to {format}...")

        # 2. Call MuseScore 3 headlessly using Virtual Framebuffer (xvfb-run)
        # Headless Linux servers do not have active monitors/displays, so MuseScore
        # needs xvfb-run to simulate a graphics card display.
        # Find the MuseScore binary dynamically
        mscore_bin = "mscore"
        for candidate in ["musescore3", "mscore3", "musescore", "mscore"]:
            # Check if command is available on PATH
            if subprocess.run(["which", candidate], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                mscore_bin = candidate
                break

        cmd = [
            "xvfb-run",
            "-a", # Auto-allocate free server port for Virtual Screen
            mscore_bin,
            str(input_file_path),
            "-o",
            str(output_file_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60 # Timeout after 1 minute of rendering
            )
            
            if result.returncode != 0:
                logger.error(f"MuseScore Conversion Failed. Stderr: {result.stderr}")
                raise HTTPException(
                    status_code=500,
                    detail=f"MuseScore failed during generation. Error: {result.stderr}"
                )
                
            if not output_file_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail="MuseScore finished but output file was not created."
                )

            # 3. Stream the file back to the browser.
            # We copy it out of the temp directory so it doesn't get auto-deleted
            # before the response is fully streamed.
            persistent_temp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{format}")
            persistent_temp.write(output_file_path.read_bytes())
            persistent_temp.close()
            
            media_types = {
                "pdf": "application/pdf",
                "mp3": "audio/mpeg",
                "mid": "audio/midi",
                "wav": "audio/wav"
            }
            
            return FileResponse(
                persistent_temp.name,
                media_type=media_types.get(format, "application/octet-stream"),
                filename=f"score.{format}"
            )
            
        except subprocess.TimeoutExpired:
            logger.error("MuseScore generation timed out.")
            raise HTTPException(status_code=504, detail="Processing timed out.")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Hugging Face Spaces requires listening on port 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)
