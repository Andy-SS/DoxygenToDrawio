# 🎯 Doxygen to Draw.io Converter v2.0

A comprehensive Python tool that automatically converts source code into beautiful, interactive call graph diagrams using Doxygen and Draw.io.

## ✨ Features

- 🚀 **Fully Automated** - Runs Doxygen automatically, no manual setup required
- 🎨 **Smart Visual Design** - Intelligent color coding and layout based on function types
- 📐 **Advanced Layout Engine** - Execution sequence-aware hierarchical arrangement
- 🔗 **Optimized Connections** - Smart edge routing that avoids node overlaps and crossings
- 🌍 **Multi-Language Support** - C, C++, Python, Java, JavaScript, TypeScript, and more
- 🎯 **Collision Avoidance** - Enhanced waypoint system prevents messy diagrams
- 🔧 **Zero Configuration** - Automatically detects project type and optimizes settings
- 📱 **Cross-Platform** - Works seamlessly on macOS, Linux, and Windows

## 🚀 Quick Start (Recommended)

The easiest way to use the tool - it handles everything automatically:

```bash
# Analyze current directory and open result
python3 doxygenToDrawio.py --run-doxygen --auto-open

# Analyze specific source directory 
python3 doxygenToDrawio.py --run-doxygen --source-dir ./src --auto-open

# Custom output location
python3 doxygenToDrawio.py --run-doxygen --doxygen-html ./docs/html --auto-open

# With verbose output to see what's happening
python3 doxygenToDrawio.py --run-doxygen --auto-open --verbose
```

## 📋 Prerequisites

### Required
- **Python 3.6+**
- **Doxygen** (for generating documentation)
  ```bash
  # macOS
  brew install doxygen
  
  # Ubuntu/Debian
  sudo apt-get install doxygen
  
  # Windows
  # Download from doxygen.nl
  ```

### Optional (for call graphs)
- **Graphviz DOT** (for enhanced call graphs)
  ```bash
  # macOS
  brew install graphviz
  
  # Ubuntu/Debian
  sudo apt-get install graphviz
  
  # Windows
  # Download from graphviz.org
  ```

## 🎮 Usage Modes

### Mode 1: Fully Automated (Recommended)
Let the script handle everything:
```bash
# Analyze current directory
python3 doxygenToDrawio.py --run-doxygen --auto-open

# Analyze specific directory with custom output
python3 doxygenToDrawio.py --run-doxygen -s ./src --doxygen-html ./output/docs --auto-open
```

### Mode 2: Existing Doxygen Output
If you already have Doxygen output:
```bash
# Use existing Doxygen HTML output
python3 doxygenToDrawio.py -d ./doxygen_output/html --auto-open
```

### Mode 3: Advanced Configuration
For power users who need full control:
```bash
# Custom DOT path for call graphs
python3 doxygenToDrawio.py --run-doxygen --dot-path /usr/local/bin/dot --auto-open

# Custom everything
python3 doxygenToDrawio.py --run-doxygen -s ./source --doxygen-html ./docs/api \
  --dot-path /opt/graphviz/bin/dot -o my_project_diagram.drawio --verbose
```

## 🛠️ Command Line Reference

### Core Options
```
-d, --doxygen-dir      Doxygen output directory (default: doxygen_output/html)
-o, --output           Output Draw.io file (default: doxygen_callgraph.drawio)
-v, --verbose          Enable verbose output
--auto-open            Automatically open the generated Draw.io file
--no-prompt            Skip the prompt to open the file
```

### Integrated Doxygen Options  
```
--run-doxygen          Automatically run Doxygen before converting (recommended)
-s, --source-dir       Source code directory for analysis (default: current directory)
--doxygen-html         Doxygen HTML output directory (default: doxygen_output/html)
--dot-path             Path to DOT executable for call graphs
--find-dot             Search for DOT executable and show path
```

### Example Commands
```bash
# Basic: analyze current directory
python3 doxygenToDrawio.py --run-doxygen --auto-open

# Advanced: full customization
python3 doxygenToDrawio.py --run-doxygen -s ./src --doxygen-html ./docs \
  --dot-path /usr/local/bin/dot -o project_flowchart.drawio --auto-open

# Existing Doxygen output
python3 doxygenToDrawio.py -d ./existing_docs/html --auto-open

# Find DOT executable location
python3 doxygenToDrawio.py --find-dot
```

## 🎨 Visual Design Features

### Function Color Coding
Our intelligent analysis categorizes functions and applies semantic colors:

- 🔴 **Red** - Entry points (`main`, `__main__`, critical paths)
- 🟢 **Green** - Initialization (`__init__`, `setup`, `constructor`)
- 🟣 **Light Green** - Configuration (`config`, `initialize`) 
- 🟡 **Yellow** - Error handling (`error`, `exception`, `catch`)
- 🟣 **Purple** - Testing (`test`, `assert`, `unittest`)
- 🔵 **Blue** - I/O operations (`read`, `write`, `input`, `output`)
- 🟠 **Orange** - Timing (`delay`, `timer`, `wait`, `sleep`)
- 🟦 **Teal** - Utilities (`get`, `set`, `helper`, `util`)
- 🔵 **Light Blue** - Regular processing functions

### Connection Styles
- **Thick blue lines** - Main execution paths from entry points
- **Dashed red lines** - Error handling flows
- **Curved lines** - Lateral (same-level) function calls
- **Orange dashed** - Callback/recursion patterns
- **Varying thickness** - Indicates importance and call frequency

### Smart Layout Engine
- **Execution sequence ordering** - Functions arranged by typical execution flow
- **Hierarchical levels** - Clear top-down program flow visualization
- **Collision avoidance** - Intelligent waypoints prevent line overlaps
- **Isolated function area** - Separate section for unconnected functions
- **Dynamic spacing** - Automatically adjusts for project size

## 🔧 Advanced Features

### Automatic Project Detection
The tool automatically detects your project type and optimizes accordingly:
- **C/C++ projects** - Optimized for header/source relationships
- **Python projects** - Handles modules, classes, and functions
- **Java projects** - Package and class structure awareness
- **JavaScript/TypeScript** - Modern JS patterns and async flows
- **Mixed projects** - Intelligent handling of multiple languages

### Smart Doxygen Configuration
When using `--run-doxygen`, the tool:
- Creates optimized Doxyfile automatically
- Detects source file patterns
- Configures call graph generation
- Sets up proper output directories
- Handles DOT executable detection
- Optimizes for your specific project type

### Enhanced Connection Routing
- **Horizontal routing** - Prevents overlaps with intelligent waypoints
- **Stepped routing** - Clean paths for complex hierarchies  
- **Side routing** - Special handling for upward/callback flows
- **Multi-point paths** - Smooth curves for long connections
- **Buffer zones** - Maintains proper spacing around nodes

## 📁 Project Structure

### With Integrated Doxygen (Recommended)
```
your_project/
├── src/                    # Your source code
│   ├── main.c
│   ├── utils.c
│   └── ...
├── doxygenToDrawio.py      # This script
└── (output generated automatically)
    ├── doxygen_output/     # Created automatically
    │   └── html/
    │       ├── *.dot       # Call graph files
    │       └── ...
    └── doxygen_callgraph.drawio  # Final diagram
```

### With Existing Doxygen Output
```
your_project/
├── doxygen_output/
│   └── html/
│       ├── *.dot           # Call graph files (what we need)
│       ├── index.html
│       └── ...
├── doxygenToDrawio.py      # This script
└── doxygen_callgraph.drawio   # Generated diagram
```

## 🎯 Output & Results

### Generated Files
- **`.drawio` file** - Ready to import into app.diagrams.net
- **Doxyfile** - Auto-generated Doxygen configuration (if using `--run-doxygen`)
- **Doxygen documentation** - Complete HTML documentation with call graphs
- **Backup files** - `.backup` versions of modified Doxyfiles

### Terminal Output
The script provides rich colored terminal feedback:
- ✅ **Green** - Success messages and confirmations
- � **Yellow** - Progress updates and warnings  
- 🔵 **Blue** - Configuration and setup information
- � **Red** - Errors and critical issues
- 🟣 **Cyan** - Statistics and file locations

### Statistics Reported
- Total nodes (functions) processed
- Total edges (function calls) found
- Number of DOT files combined
- Source files analyzed
- Output file location
- Performance metrics

## 🔍 Troubleshooting

### Installation Issues

**Doxygen not found**
```bash
# macOS
brew install doxygen

# Ubuntu/Debian  
sudo apt-get install doxygen

# Windows
# Download from doxygen.nl
```

**DOT/Graphviz not found**
```bash
# Find existing DOT installation
python3 doxygenToDrawio.py --find-dot

# Install Graphviz
# macOS: brew install graphviz
# Ubuntu: sudo apt-get install graphviz
# Windows: Download from graphviz.org

# Use custom DOT path
python3 doxygenToDrawio.py --run-doxygen --dot-path /usr/local/bin/dot
```

### Common Issues

**No DOT files generated**
- Solution: Ensure your code has function calls between different functions
- Check: Use `--verbose` to see detailed Doxygen output
- Verify: DOT is properly installed and detected

**Empty or minimal diagram**
- Cause: Static analysis can only show existing relationships
- Solution: Ensure functions actually call each other in your code
- Tip: Add some function calls to create meaningful graphs

**Directory not created correctly**
- Issue: Output directories created in wrong location
- Solution: Use absolute paths or check current working directory
- Example: `--doxygen-html ./output/docs` vs `/full/path/to/output/docs`

**Large project performance**
- For 1000+ functions: Use Doxygen filtering options
- Consider: Focus on specific modules with `INPUT` patterns in Doxyfile
- Optimize: Use `--no-prompt` for batch processing

### Error Messages & Solutions

```
Error: Source directory './src' does not exist
```
**Solution**: Specify correct source directory with `-s` or `--source-dir`

```
Error: Doxygen not found in system PATH
```
**Solution**: Install Doxygen or add it to your PATH

```
Error: No .dot files found in output directory
```
**Solution**: Ensure DOT is installed and call graphs are enabled

```
Error: Expected output directory not found
```
**Solution**: Check directory paths and permissions

## 📱 Opening Your Diagram

### Auto-Opening Options

The script intelligently handles file opening across platforms:

#### 🖥️ **Desktop Applications**
- **macOS**: `draw.io` app → default app → browser
- **Linux**: `drawio` command → `xdg-open` → browser  
- **Windows**: `draw.io.exe` → default app → browser

#### 🌐 **Web Browser**
- Opens `app.diagrams.net` automatically
- Provides instructions for manual file loading
- No plugins or extensions required

#### ⚙️ **Manual Opening**
1. Go to [app.diagrams.net](https://app.diagrams.net)
2. Click "Open Existing Diagram"  
3. Select your `.drawio` file
4. Enjoy your interactive call graph!

### Opening Behavior
```bash
# Prompt to open (default)
python3 doxygenToDrawio.py --run-doxygen

# Auto-open immediately  
python3 doxygenToDrawio.py --run-doxygen --auto-open

# Skip open prompt entirely
python3 doxygenToDrawio.py --run-doxygen --no-prompt
```

## 🆚 Why This Tool?

### vs. Manual DOT Processing
- ❌ **Manual**: Requires shell scripts, manual file combining, complex setup
- ✅ **This tool**: Single command, automatic processing, cross-platform

### vs. Other Converters  
- ❌ **Others**: Limited styling, basic layouts, manual configuration
- ✅ **This tool**: Intelligent styling, execution-aware layout, zero config

### vs. Online Tools
- ❌ **Online**: Privacy concerns, file size limits, no automation
- ✅ **This tool**: Local processing, unlimited size, full automation

### Key Advantages
- 🚀 **Zero Setup** - Works out of the box
- 🎨 **Professional Output** - Publication-ready diagrams
- 🔄 **Reproducible** - Same input = same output
- 🌍 **Universal** - Works with any language Doxygen supports
- 🔧 **Extensible** - Easy to modify and customize

## 🤝 Contributing

We welcome contributions! Areas for improvement:
- Additional language-specific optimizations
- Enhanced layout algorithms  
- More connection routing options
- Custom styling themes
- Performance optimizations

## 📜 License

This project is open source. Feel free to use, modify, and distribute.

## 🙏 Credits

Built with:
- **Doxygen** - Documentation generation
- **Graphviz DOT** - Graph layout algorithms  
- **Draw.io** - Interactive diagram platform
- **Python** - Automation and processing
