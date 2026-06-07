# Use lightweight python base image
FROM python:3.10-slim

# Set environment variables to avoid python buffering and logs loss
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    HOME=/home/user

# Install system dependencies including MuseScore 3, Virtual Framebuffer (Xvfb), and Soundfonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    musescore3 \
    xvfb \
    fluid-soundfont-gm \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set up a new non-root user (Hugging Face Spaces runs containers as user ID 1000)
# This prevents permission errors during file generation.
RUN useradd -m -u 1000 user
USER user
ENV PATH=/home/user/.local/bin:$PATH

# Configure working directory
WORKDIR /home/user/app

# Install Python API libraries
RUN pip install --no-cache-dir fastapi uvicorn python-multipart jinja2

# Copy the app script to the container
COPY --chown=user:user app.py /home/user/app/app.py

# Expose the mandatory Hugging Face port
EXPOSE 7860

# Command to run the application
CMD ["python", "app.py"]
