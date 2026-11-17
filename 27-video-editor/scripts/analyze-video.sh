#!/bin/bash
# analyze-video.sh - Analyze video for strategic B-roll insertion points
# Uses scene detection to find natural transition points
# Usage: analyze-video.sh --input video.mp4 --output analysis.json

set -e

INPUT=""
OUTPUT="analysis.json"
METHOD="content"  # content or threshold
MIN_SCENE_LEN="2.0"

while [[ $# -gt 0 ]]; do
  case $1 in
    --input)
      INPUT="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    --method)
      METHOD="$2"
      shift 2
      ;;
    --min-scene-len)
      MIN_SCENE_LEN="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$INPUT" ]]; then
  echo "Usage: analyze-video.sh --input <video.mp4> [--output analysis.json] [--method content|threshold]"
  echo ""
  echo "This script detects scene changes and suggests B-roll insertion points."
  exit 1
fi

# Check if scenedetect is installed
if ! command -v scenedetect &> /dev/null; then
  echo "ERROR: scenedetect not found. Install it with: bash ~/.openclaw/skills/shared-utils/oc-python.sh pip-install scenedetect"
  exit 1
fi

echo "Analyzing video for scene changes..."
echo "Input: $INPUT"
echo "Method: $METHOD"
echo ""

# Create temp directory
TEMP_DIR="/tmp/video_analyze_$(date +%s)"
mkdir -p "$TEMP_DIR"

# Run scene detection
if [[ "$METHOD" == "content" ]]; then
  scenedetect -i "$INPUT" detect-content -t 30 detect-adaptive -t 3 list-scenes -o "$TEMP_DIR/scenes.csv"
else
  scenedetect -i "$INPUT" detect-threshold -t 12 list-scenes -o "$TEMP_DIR/scenes.csv"
fi

# Parse results and create JSON analysis
python3 << PYTHON_EOF
import csv
import json
import sys

scenes = []
suggested_broll_points = []

# Read scene detection output
csv_path = "$TEMP_DIR/scenes.csv"
try:
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            scene_num = row.get('Scene Number', '').strip()
            start_time = row.get('Start Time (seconds)', '').strip()
            end_time = row.get('End Time (seconds)', '').strip()
            duration = row.get('Length (seconds)', '').strip()
            
            if scene_num and start_time:
                scenes.append({
                    'scene_number': int(scene_num),
                    'start_time': float(start_time),
                    'end_time': float(end_time) if end_time else None,
                    'duration': float(duration) if duration else None
                })
                
                # Suggest B-roll insertion at scene boundaries (after first few seconds)
                if float(start_time) > 5:  # Skip very beginning
                    suggested_broll_points.append({
                        'timestamp': float(start_time),
                        'reason': f'Scene change (Scene {scene_num})',
                        'suggested_duration': min(5.0, float(duration)) if duration else 5.0
                    })
except FileNotFoundError:
    print("Warning: Could not find scene detection output", file=sys.stderr)

# Create analysis output
analysis = {
    'video': '$INPUT',
    'total_scenes': len(scenes),
    'scenes': scenes,
    'suggested_broll_insertion_points': suggested_broll_points[:5],  # Top 5 suggestions
    'method_used': '$METHOD'
}

with open('$OUTPUT', 'w') as f:
    json.dump(analysis, f, indent=2)

print(f"Analysis saved to: $OUTPUT")
print(f"Detected {len(scenes)} scenes")
print(f"Suggested {len(suggested_broll_points[:5])} B-roll insertion points")
PYTHON_EOF

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "Analysis complete. Check $OUTPUT for results."