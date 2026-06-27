#!/bin/bash
# Tijah MVP Setup Script

echo "================================"
echo "  Tijah MVP Setup"
echo "  WhatsApp Shop Manager"
echo "================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "ERROR: Python 3.9+ is required. Install from https://python.org"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo "Using Python: $PYTHON"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
$PYTHON -m venv venv

# Activate
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "Created .env file from template."
    echo "IMPORTANT: Edit .env with your API keys before running!"
fi

echo ""
echo "================================"
echo "  Setup Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys"
echo "  2. Test locally:  python test_local.py"
echo "  3. Run server:    python run.py"
echo "  4. Set up WhatsApp webhook to: https://your-domain.com/webhook"
echo ""
echo "Cost estimate (per 1000 users/day):"
echo "  Gemini Flash:  ~\$0.01/day (NLU parsing)"
echo "  Whisper:       ~\$0.50/day (voice transcription)"
echo "  edge-tts:      FREE (text-to-speech)"
echo "  SQLite:        FREE (database)"
echo "  VPS hosting:   ~\$5/month"
echo ""
