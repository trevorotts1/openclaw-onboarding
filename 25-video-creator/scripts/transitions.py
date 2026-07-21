#!/usr/bin/env python3
"""
Transitions Library
Video transition effects for clip assembly.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent))


class Transitions:
    """Collection of video transition effects."""
    
    AVAILABLE = [
        'fade',
        'slide_left', 'slide_right', 'slide_up', 'slide_down',
        'wipe_left', 'wipe_right', 'wipe_up', 'wipe_down',
        'none'
    ]
    
    @staticmethod
    def fade(clip1, clip2, duration: float = 0.5):
        """Crossfade between two clips."""
        from moviepy.video.fx.all import fadein, fadeout
        
        clip1 = clip1.fadeout(duration)
        clip2 = clip2.fadein(duration)
        return [clip1, clip2]
    
    @staticmethod
    def slide(clip1, clip2, direction: str, duration: float = 0.5):
        """Slide transition."""
        from moviepy.video.compositing.transitions import slide_in
        
        sides = {
            'left': 'left',
            'right': 'right',
            'up': 'top',
            'down': 'bottom'
        }
        
        side = sides.get(direction, 'left')
        clip2 = slide_in(clip2, duration=duration, side=side)
        
        # Overlap clips during transition
        return [clip1.set_end(clip1.duration - duration), clip2]
    
    @staticmethod
    def wipe(clip1, clip2, direction: str, duration: float = 0.5):
        """Wipe transition using mask."""
        import numpy as np
        from moviepy.editor import CompositeVideoClip, VideoClip
        
        w, h = clip1.size
        
        def make_mask(t):
            """Generate wipe mask."""
            progress = t / duration
            mask = np.zeros((h, w))
            
            if direction == 'right':
                cutoff = int(w * progress)
                mask[:, :cutoff] = 1
            elif direction == 'left':
                cutoff = int(w * (1 - progress))
                mask[:, cutoff:] = 1
            elif direction == 'down':
                cutoff = int(h * progress)
                mask[:cutoff, :] = 1
            elif direction == 'up':
                cutoff = int(h * (1 - progress))
                mask[cutoff:, :] = 1
            
            return mask
        
        # Create transition composite
        c1_end = clip1.subclip(clip1.duration - duration, clip1.duration)
        c2_start = clip2.subclip(0, duration)
        
        c2_masked = c2_start.set_make_frame(
            lambda t: c2_start.get_frame(t) * make_mask(t)[:, :, np.newaxis]
        )
        c1_masked = c1_end.set_make_frame(
            lambda t: c1_end.get_frame(t) * (1 - make_mask(t))[:, :, np.newaxis]
        )
        
        transition = CompositeVideoClip([c1_masked, c2_masked], size=clip1.size)
        
        return [
            clip1.subclip(0, clip1.duration - duration),
            transition,
            clip2.subclip(duration)
        ]
    
    @staticmethod
    def zoom(clip1, clip2, direction: str, duration: float = 0.5):
        """Zoom transition."""
        from moviepy.video.fx.all import resize
        
        if direction == 'in':
            # Zoom in on end of clip1
            c1_end = clip1.subclip(clip1.duration - duration, clip1.duration)
            c1_zoomed = c1_end.fx(resize, lambda t: 1 + 0.5 * t / duration)
            return [clip1.subclip(0, clip1.duration - duration), c1_zoomed, clip2]
        
        else:  # zoom out
            # Zoom out from start of clip2
            c2_start = clip2.subclip(0, duration)
            c2_zoomed = c2_start.fx(resize, lambda t: 1.5 - 0.5 * t / duration)
            return [clip1, c2_zoomed, clip2.subclip(duration)]
    
    @staticmethod
    def flip(clip1, clip2, axis: str, duration: float = 0.5):
        """Reject the unimplemented flip effect instead of substituting a fade."""
        raise ValueError(f"Unsupported transition: flip_{axis}")
    
    @staticmethod
    def apply_transition(clip1, clip2, transition_type: str, duration: float = 0.5):
        """
        Apply specified transition between two clips.
        
        Args:
            clip1: First clip
            clip2: Second clip
            transition_type: Type of transition
            duration: Transition duration
            
        Returns:
            List of clips with transition applied
        """
        if transition_type not in Transitions.AVAILABLE:
            raise ValueError(f"Unsupported transition: {transition_type}")

        if transition_type == 'none' or duration <= 0:
            return [clip1, clip2]
        
        elif transition_type == 'fade':
            return Transitions.fade(clip1, clip2, duration)
        
        elif transition_type.startswith('slide_'):
            direction = transition_type.replace('slide_', '')
            return Transitions.slide(clip1, clip2, direction, duration)
        
        elif transition_type.startswith('wipe_'):
            direction = transition_type.replace('wipe_', '')
            return Transitions.wipe(clip1, clip2, direction, duration)
        
        raise ValueError(f"Unsupported transition: {transition_type}")


def preview_transition(transition_type: str, duration: float = 2.0, 
                      output: Path = None) -> Path:
    """
    Create a preview video showing the transition.
    
    Args:
        transition_type: Type of transition to preview
        duration: Preview clip duration
        output: Output file path
        
    Returns:
        Path to preview video
    """
    if transition_type not in Transitions.AVAILABLE:
        raise ValueError(f"Unsupported transition: {transition_type}")

    from moviepy.editor import ColorClip, concatenate_videoclips
    
    if output is None:
        output = Path(f"transition_{transition_type}_preview.mp4")
    
    # Create two colored clips
    clip1 = ColorClip(size=(1920, 1080), color=(100, 50, 50)).set_duration(duration)
    clip2 = ColorClip(size=(1920, 1080), color=(50, 50, 100)).set_duration(duration)
    
    # Apply transition
    transitioned = Transitions.apply_transition(clip1, clip2, transition_type, 1.0)
    
    # Concatenate
    final = concatenate_videoclips(transitioned, method="compose")
    
    final.write_videofile(str(output), fps=30, codec='libx264')
    final.close()
    
    print(f"✓ Preview saved: {output}")
    return output


def list_transitions():
    """Display available transitions."""
    print("Available transitions:")
    print()
    print("Basic:")
    print("  fade - Smooth fade between clips")
    print("  none - Hard cut")
    print()
    print("Slide:")
    print("  slide_left, slide_right, slide_up, slide_down")
    print()
    print("Wipe:")
    print("  wipe_left, wipe_right, wipe_up, wipe_down")


def main():
    parser = argparse.ArgumentParser(description='Video transitions library')
    parser.add_argument('--list', '-l', action='store_true', 
                       help='List available transitions')
    parser.add_argument('--preview', '-p', choices=Transitions.AVAILABLE,
                       help='Preview a transition type')
    parser.add_argument('--duration', type=float, default=2.0,
                       help='Preview clip duration')
    parser.add_argument('--output', '-o', type=Path,
                       help='Output file for preview')
    
    args = parser.parse_args()
    
    if args.list:
        list_transitions()
        return 0
    
    if args.preview:
        try:
            result = preview_transition(args.preview, args.duration, args.output)
            print(f"🎬 Preview: {result}")
            return 0
        except Exception as e:
            print(f"✗ Error: {e}")
            return 1
    
    # No args - show help
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
