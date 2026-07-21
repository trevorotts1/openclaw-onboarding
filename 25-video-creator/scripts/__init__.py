"""Video Creator Skill

Create videos from scratch using AI models and basic editing tools.
"""

from pathlib import Path

_skill_version = (
    Path(__file__).resolve().parent.parent / "skill-version.txt"
).read_text(encoding="utf-8").strip()
__version__ = _skill_version[1:] if _skill_version.startswith("v") else _skill_version
__author__ = "OpenClaw"

# Core imports
from .ai_providers import AIProvider
from .text_to_video import text_to_video
from .script_to_video import script_to_video
from .image_to_video import image_to_video
from .multi_clip_assembly import assemble_clips
from .add_music import add_music
from .template_video import TemplateEngine
from .transitions import Transitions

__all__ = [
    'AIProvider',
    'text_to_video',
    'script_to_video', 
    'image_to_video',
    'assemble_clips',
    'add_music',
    'TemplateEngine',
    'Transitions',
]


class VideoCreator:
    """
    Main Video Creator interface.
    
    Provides a unified API for all video creation capabilities.
    """
    
    def __init__(self, config_path: Path = None):
        """
        Initialize Video Creator.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path or (Path.home() / ".openclaw" / "video-creator" / "config.json")
        self.config = self._load_config()
        
    def _load_config(self):
        """Load configuration from file."""
        import json
        if self.config_path.exists():
            with open(self.config_path) as f:
                return json.load(f)
        return {}
    
    def text_to_video(self, prompt: str, **kwargs):
        """Generate video from text description."""
        return text_to_video(prompt, **kwargs)
    
    def script_to_video(self, script_path: Path, **kwargs):
        """Convert script to video."""
        return script_to_video(script_path, **kwargs)
    
    def image_to_video(self, image_path: Path, **kwargs):
        """Animate image to video."""
        return image_to_video(image_path, **kwargs)
    
    def assemble(self, clips: list, **kwargs):
        """Assemble multiple clips."""
        return assemble_clips(clips, **kwargs)
    
    def add_music(self, video_path: Path, **kwargs):
        """Add music to video."""
        return add_music(video_path, **kwargs)
    
    def from_template(self, template_name: str, data: dict):
        """Generate video from template."""
        engine = TemplateEngine(template_name, data)
        return engine.generate()
