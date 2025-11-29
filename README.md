# PDF2Muse 🎶

PDF2Muse is a modern Python tool that converts PDF files of sheet music into MusicXML 🎼 and MuseScore (.mscx) files using optical music recognition (OMR). It leverages the power of the [oemer](https://github.com/BreezeWhite/oemer) library to transcribe music from PDFs.

## ✨ Features

- **Easy to use**: Simple command-line interface and web UI
- **High quality**: Uses state-of-the-art optical music recognition
- **Flexible output**: Generates both MusicXML and MuseScore formats
- **Modern architecture**: Built with modern Python best practices
- **Beautiful output**: Rich terminal output with progress indicators

## 🙏 Acknowledgements

This project would not have been possible without the excellent work done by the [oemer](https://github.com/BreezeWhite/oemer) project. We extend our sincere gratitude to the oemer team for creating such a powerful and versatile optical music recognition library.

## ⚙️ Requirements

- Python 3.9 or higher 🐍
- Poppler (for PDF to image conversion)

## ⬇️ Installation

### Quick Install

```bash
pip install -e .
```

### Development Install

```bash
pip install -e ".[dev]"
```

The package will automatically install all required dependencies including:
- oemer (optical music recognition)
- pdf2image (PDF conversion)
- typer (CLI framework)
- gradio (web interface)
- rich (beautiful terminal output)

### Installing Poppler

Poppler is required for PDF to image conversion:

**Windows:**
```bash
# Using Chocolatey
choco install poppler

# Or download from: https://github.com/oschwartz10612/poppler-windows/releases/
```

**macOS:**
```bash
brew install poppler
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install poppler-utils
```

## 🚀 Usage

### Command Line Interface

**Convert a PDF file:**
```bash
pdf2muse convert sheet_music.pdf
```

**Specify output directory:**
```bash
pdf2muse convert sheet_music.pdf --output ./my_output
```

**Disable deskewing:**
```bash
pdf2muse convert sheet_music.pdf --no-deskew
```

**Use TensorFlow instead of ONNX:**
```bash
pdf2muse convert sheet_music.pdf --use-tf
```

**Enable verbose logging:**
```bash
pdf2muse convert sheet_music.pdf --verbose
```

**Show help:**
```bash
pdf2muse --help
pdf2muse convert --help
```

### Web Interface

Launch the Gradio web UI:
```bash
pdf2muse ui
```

With custom port:
```bash
pdf2muse ui --port 8080
```

Create a public shareable link:
```bash
pdf2muse ui --share
```

### Download Models

Pre-download the oemer model checkpoints:
```bash
pdf2muse download-models
```

Force re-download:
```bash
pdf2muse download-models --force
```

## 📦 Package Structure

```
PDF2Muse/
├── src/
│   └── pdf2muse/
│       ├── __init__.py       # Package initialization
│       ├── cli.py            # Typer CLI entry point
│       ├── core.py           # Main processing pipeline
│       ├── oemer_utils.py    # Oemer wrapper utilities
│       ├── musicxml.py       # MusicXML manipulation
│       └── ui.py             # Gradio web interface
├── pyproject.toml            # Project metadata & dependencies
├── README.md                 # This file
└── .gitignore
```

## 🔧 Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src/
```

### Linting

```bash
ruff check src/
```

## 📝 How It Works

1. **PDF to Images**: Converts each page of the PDF to a high-resolution PNG image
2. **OMR Processing**: Runs oemer on each image to extract musical notation
3. **MusicXML Generation**: Combines the recognized music into MusicXML format
4. **MuseScore Conversion**: Converts the MusicXML to MuseScore's .mscx format

## 🎯 Best Results

For optimal recognition quality:
- Use high-resolution scans (300 DPI or higher)
- Ensure clear, uncluttered sheet music
- Use standard Western music notation
- Avoid handwritten scores (printed music works best)

## 🐛 Troubleshooting

**Import Error: No module named 'pdf2muse'**
- Make sure you installed the package: `pip install -e .`

**Command not found: pdf2muse**
- Ensure your Python scripts directory is in your PATH
- Try running: `python -m pdf2muse.cli` instead

**Poppler error during conversion**
- Install Poppler (see Installation section above)
- On Windows, add Poppler's bin directory to your PATH

**No MusicXML files generated**
- Check that your PDF contains clear sheet music
- Try enabling verbose mode: `pdf2muse convert file.pdf --verbose`
- Ensure oemer checkpoints are downloaded: `pdf2muse download-models`

## 📜 License

MIT License - see LICENSE file for details.

## 🔗 Links

- **Homepage**: https://github.com/thedivergentai/PDF2Muse
- **Issues**: https://github.com/thedivergentai/PDF2Muse/issues
- **oemer Library**: https://github.com/BreezeWhite/oemer
