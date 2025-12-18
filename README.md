# AI-Powered Java Tutor 🎓

An interactive Java learning platform powered by Claude AI with real-time code execution and adaptive quizzes.

## Features

- **AI Chat Tutor** - Ask questions and get instant explanations
- **Code Execution** - Write and run Java code in your browser
- **Interactive Quizzes** - Test your knowledge with AI-generated questions
- **Progress Tracking** - Monitor your learning progress

## Tech Stack

- **Backend:** Python, Flask, SQLite
- **Frontend:** HTML, CSS, JavaScript
- **AI:** DeepSeek-Coder
- **Infrastructure:** Docker, Nginx, AWS EC2
- **CI/CD:** GitHub Actions

## Quick Start

### Prerequisites
- Python 3.10+
- Docker

### Run Locally

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/Java-Tutor.git
cd Java-Tutor

# Install dependencies
pip install -r requirements.txt

# Pull Java Docker image
docker pull eclipse-temurin:17-jdk

# Run application
cd backend
python app.py
```

Visit `http://localhost:80`

## Deploy to AWS EC2

```bash
# Install Docker and Nginx
sudo apt update
sudo apt install docker.io nginx -y

# Clone and build
git clone https://github.com/Rahul-069/Java-Tutor.git
cd Java-Tutor
docker build -t java-tutor-app .

# Run container
docker run -d -p 8080:8080 \
  --name java-tutor-app \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /tmp:/tmp \
  java-tutor-app

# Configure Nginx as reverse proxy (port 80 → 8080)
# Setup instructions: See deployment guide in docs
```

## Project Structure

```
Java-Tutor/
├── backend/
│   ├── app.py              # Main application
│   ├── database.py         # Database operations
│   ├── metrics_tracker.py
│   ├── model_handler.py
│   └── tests/              # Test suite
├── frontend/
│   ├── index.html          # Main UI
│   ├── login.html
│   ├── signup.html
│   └── css/             # Styling and scripts
│   └── js/
├── Dockerfile
└── requirements.txt
```

## Key Features

### Secure Code Execution
- Docker-based sandbox with resource limits
- Network isolation
- 10-second timeout protection

### CI/CD Pipeline
- Automated testing with pytest
- Automatic deployment to EC2
- Rollback on failure
