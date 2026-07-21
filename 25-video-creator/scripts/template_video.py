#!/usr/bin/env python3
"""
Template Video Generator
Create videos using pre-built templates for common formats.
"""

import argparse
import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from text_to_video import text_to_video
from image_to_video import image_to_video
from multi_clip_assembly import assemble_clips
from add_music import add_music


class TemplateEngine:
    """Engine for processing video templates."""
    
    TEMPLATES = {
        'product_showcase': 'product_showcase',
        'social_post': 'social_post',
        'tutorial': 'tutorial',
        'testimonial': 'testimonial',
        'podcast_clip': 'podcast_clip',
        'event_promo': 'event_promo',
        'announcement': 'announcement',
    }
    
    def __init__(self, template_name: str, data: Dict[str, Any],
                 output: Optional[Path] = None):
        self.template_name = template_name.lower()
        self.data = data
        self.output = output
        self.output_dir = Path("output")
        self.temp_clips = []
        
    def generate(self) -> Path:
        """Generate video from template."""
        print(f"🎨 Using template: {self.template_name}")

        self._validate_data()
        self._resolve_output("placeholder.mp4").parent.mkdir(parents=True, exist_ok=True)
        
        if self.template_name == 'product_showcase':
            return self._product_showcase()
        elif self.template_name == 'social_post':
            return self._social_post()
        elif self.template_name == 'tutorial':
            return self._tutorial()
        elif self.template_name == 'testimonial':
            return self._testimonial()
        elif self.template_name == 'podcast_clip':
            return self._podcast_clip()
        elif self.template_name == 'event_promo':
            return self._event_promo()
        elif self.template_name == 'announcement':
            return self._announcement()
        else:
            raise ValueError(f"Unknown template: {self.template_name}")

    def _validate_data(self) -> None:
        """Validate required client data before any rendering begins."""
        if self.template_name not in self.TEMPLATES:
            raise ValueError(f"Unknown template: {self.template_name}")
        if not isinstance(self.data, dict):
            raise ValueError("Template data must be a JSON object")

        required_strings = {
            'product_showcase': ('product_name',),
            'social_post': ('headline',),
            'tutorial': ('title',),
            'testimonial': ('quote', 'author'),
            'podcast_clip': ('audio_file',),
            'event_promo': ('event_name', 'date', 'location', 'description'),
            'announcement': ('title', 'message'),
        }
        allowed_fields = {
            'product_showcase': {
                'product_name', 'images', 'features', 'tagline', 'price',
                'call_to_action', 'music', 'duration',
            },
            'social_post': {
                'headline', 'subheadline', 'platform', 'duration', 'music',
            },
            'tutorial': {'title', 'instructor', 'sections', 'music'},
            'testimonial': {
                'quote', 'author', 'title', 'company', 'duration',
            },
            'podcast_clip': {
                'audio_file', 'quote_text', 'speaker', 'podcast_name', 'duration',
            },
            'event_promo': {'event_name', 'date', 'location', 'description'},
            'announcement': {'title', 'message', 'duration'},
        }
        unsupported_fields = sorted(set(self.data) - allowed_fields[self.template_name])
        if unsupported_fields:
            raise ValueError(
                f"Unsupported field(s) for template '{self.template_name}': "
                + ", ".join(unsupported_fields)
            )
        for field_name in required_strings[self.template_name]:
            value = self.data.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Missing required non-empty field '{field_name}' "
                    f"for template '{self.template_name}'"
                )

        if self.template_name == 'product_showcase':
            self._validate_nonempty_string_list('features')
            images = self._validate_nonempty_string_list('images')
            missing_images = [path for path in images if not Path(path).is_file()]
            if missing_images:
                raise ValueError(
                    "Required product image file(s) not found: "
                    + ", ".join(missing_images)
                )

        if self.template_name == 'tutorial':
            sections = self.data.get('sections')
            if not isinstance(sections, list) or not sections:
                raise ValueError(
                    "Missing required non-empty field 'sections' for template 'tutorial'"
                )
            for index, section in enumerate(sections, start=1):
                if not isinstance(section, dict):
                    raise ValueError(f"Tutorial section {index} must be an object")
                for field_name in ('heading', 'content'):
                    value = section.get(field_name)
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(
                            f"Tutorial section {index} requires non-empty '{field_name}'"
                        )
                duration = section.get('duration')
                if not isinstance(duration, (int, float)) or duration <= 0:
                    raise ValueError(
                        f"Tutorial section {index} requires a positive 'duration'"
                    )

        if self.template_name == 'social_post':
            platform = self.data.get('platform', 'instagram')
            supported_platforms = {
                'instagram', 'tiktok', 'reels', 'youtube', 'twitter', 'linkedin'
            }
            if platform not in supported_platforms:
                raise ValueError(f"Unsupported social platform: {platform}")

        if self.template_name == 'podcast_clip':
            audio_path = Path(self.data['audio_file'])
            if not audio_path.is_file():
                raise ValueError(f"Required audio_file not found: {audio_path}")

        music = self.data.get('music')
        if music is not None:
            if not isinstance(music, str) or not music.strip():
                raise ValueError("Template field 'music' must be a non-empty file path")
            if not Path(music).is_file():
                raise ValueError(f"Requested music file not found: {music}")

        duration = self.data.get('duration')
        if duration is not None and (
            not isinstance(duration, (int, float)) or duration <= 0
        ):
            raise ValueError("Template field 'duration' must be a positive number")

    def _validate_nonempty_string_list(self, field_name: str):
        value = self.data.get(field_name)
        if (not isinstance(value, list) or not value
                or any(not isinstance(item, str) or not item.strip() for item in value)):
            raise ValueError(
                f"Missing required non-empty string list '{field_name}' "
                f"for template '{self.template_name}'"
            )
        return value

    def _resolve_output(self, default_name: str) -> Path:
        """Use the requested output path, or the template's deterministic default."""
        if self.output is not None:
            return Path(self.output)
        return self.output_dir / default_name
    
    def _product_showcase(self) -> Path:
        """Generate product showcase video."""
        from moviepy.editor import (ColorClip, TextClip, ImageClip, 
                                   CompositeVideoClip, concatenate_videoclips)
        
        product_name = self.data['product_name']
        tagline = self.data.get('tagline', '')
        images = self.data['images']
        features = self.data['features']
        price = self.data.get('price', '')
        cta = self.data.get('call_to_action', '')
        duration = self.data.get('duration', 30)
        
        clips = []
        section_count = len(images) + 2 + int(bool(price or cta))
        section_duration = duration / section_count
        
        # Intro
        intro = self._create_text_slide(
            f"{product_name}\n{tagline}",
            section_duration,
            bg_color=(30, 40, 60)
        )
        clips.append(intro)
        
        # Product images
        for img_path in images:
            img_clip = (ImageClip(str(img_path))
                       .set_duration(section_duration)
                       .resize(height=800))
            clips.append(img_clip)
        
        # Features
        features_text = "Features:\n" + "\n".join(f"• {f}" for f in features)
        features_clip = self._create_text_slide(features_text, section_duration)
        clips.append(features_clip)
        
        # CTA
        if price or cta:
            cta_text = f"{price}\n\n{cta}" if price and cta else price or cta
            cta_clip = self._create_text_slide(
                cta_text, section_duration, bg_color=(60, 100, 60)
            )
            clips.append(cta_clip)
        
        # Assemble
        final = concatenate_videoclips(clips, method="compose")
        
        # Add music
        if self.data.get('music'):
            final = self._add_music_track(final, self.data['music'])
        
        output = self._resolve_output(
            f"{product_name.lower().replace(' ', '_')}_showcase.mp4"
        )
        final.write_videofile(str(output), fps=30, codec='libx264', audio_codec='aac')
        final.close()
        
        return output
    
    def _social_post(self) -> Path:
        """Generate social media optimized video."""
        from moviepy.editor import ColorClip, TextClip, CompositeVideoClip
        
        platform = self.data.get('platform', 'instagram')
        headline = self.data['headline']
        subheadline = self.data.get('subheadline', '')
        duration = self.data.get('duration', 15)
        
        # Platform-specific dimensions
        dimensions = {
            'instagram': (1080, 1080),  # Square
            'tiktok': (1080, 1920),     # Vertical
            'reels': (1080, 1920),
            'youtube': (1920, 1080),    # Horizontal
            'twitter': (1200, 675),
            'linkedin': (1200, 627),
        }
        
        width, height = dimensions.get(platform, (1080, 1080))
        
        # Create animated text video
        bg = ColorClip(size=(width, height), color=(100, 50, 150)).set_duration(duration)
        
        clips = [bg]
        
        # Headline
        if headline:
            headline_text = TextClip(
                headline,
                fontsize=80 if platform in ['instagram', 'tiktok', 'reels'] else 60,
                color='white',
                font='Arial-Bold',
                method='caption',
                size=(width - 100, None),
                align='center'
            ).set_duration(duration).set_position('center')
            clips.append(headline_text)
        
        # Subheadline
        if subheadline:
            sub_text = TextClip(
                subheadline,
                fontsize=40,
                color='yellow',
                method='caption',
                size=(width - 150, None),
                align='center'
            ).set_duration(duration - 3).set_start(3).set_position(('center', height * 0.7))
            clips.append(sub_text)
        
        video = CompositeVideoClip(clips)
        
        if self.data.get('music'):
            video = self._add_music_track(video, self.data['music'])
        
        output = self._resolve_output(
            f"social_{platform}_{int(datetime.now().timestamp())}.mp4"
        )
        video.write_videofile(str(output), fps=30, codec='libx264', audio_codec='aac')
        video.close()
        
        return output
    
    def _tutorial(self) -> Path:
        """Generate tutorial/instructional video."""
        from moviepy.editor import (ColorClip, TextClip, CompositeVideoClip,
                                   concatenate_videoclips)
        
        title = self.data['title']
        instructor = self.data.get('instructor', '')
        sections = self.data['sections']
        
        clips = []
        
        # Title card
        title_text = f"{title}\n\nwith {instructor}" if instructor else title
        title_clip = self._create_text_slide(title_text, 4, bg_color=(40, 60, 80))
        clips.append(title_clip)
        
        # Section slides
        for section in sections:
            heading = section.get('heading', '')
            content = section.get('content', '')
            sec_duration = section.get('duration', 10)
            
            display_text = f"{heading}\n\n{content}"
            slide = self._create_text_slide(display_text, sec_duration)
            clips.append(slide)
        
        # Outro
        outro = self._create_text_slide("Thanks for watching!\nSubscribe for more", 3)
        clips.append(outro)
        
        final = concatenate_videoclips(clips, method="compose")
        
        if self.data.get('music'):
            final = self._add_music_track(final, self.data['music'], volume=0.2)
        
        output = self._resolve_output(
            f"tutorial_{title.lower().replace(' ', '_')}.mp4"
        )
        final.write_videofile(str(output), fps=30, codec='libx264', audio_codec='aac')
        final.close()
        
        return output
    
    def _testimonial(self) -> Path:
        """Generate testimonial video."""
        from moviepy.editor import ColorClip, TextClip, CompositeVideoClip
        
        quote = self.data['quote']
        author = self.data['author']
        title = self.data.get('title', '')
        company = self.data.get('company', '')
        duration = self.data.get('duration', 20)
        
        width, height = 1920, 1080
        
        bg = ColorClip(size=(width, height), color=(20, 30, 40)).set_duration(duration)
        
        # Quote marks
        quote_mark = TextClip('"', fontsize=200, color=(100, 100, 100)).set_duration(duration)
        quote_mark = quote_mark.set_position((100, 100))
        
        # Main quote
        quote_text = TextClip(
            quote,
            fontsize=50,
            color='white',
            method='caption',
            size=(width - 400, None),
            align='center'
        ).set_duration(duration).set_position('center')
        
        # Author info
        author_info = f"— {author}"
        if title:
            author_info += f", {title}"
        if company:
            author_info += f"\n{company}"
        
        author_text = TextClip(
            author_info,
            fontsize=35,
            color='yellow',
            align='center'
        ).set_duration(duration).set_position(('center', height - 150))
        
        video = CompositeVideoClip([bg, quote_mark, quote_text, author_text])
        
        output = self._resolve_output(
            f"testimonial_{author.lower().replace(' ', '_')}.mp4"
        )
        video.write_videofile(str(output), fps=30, codec='libx264', audio_codec='aac')
        video.close()
        
        return output
    
    def _podcast_clip(self) -> Path:
        """Generate podcast clip/audiogram."""
        from moviepy.editor import (ColorClip, TextClip, AudioFileClip,
                                   CompositeVideoClip, CompositeAudioClip)
        
        audio_file = self.data['audio_file']
        quote_text = self.data.get('quote_text', '')
        speaker = self.data.get('speaker', '')
        podcast_name = self.data.get('podcast_name', '')
        
        # Load audio
        audio = AudioFileClip(audio_file)
        duration = min(audio.duration, self.data.get('duration', 60))
        audio = audio.subclip(0, duration)
        
        # Create visual
        width, height = 1080, 1080  # Square for social
        
        bg = ColorClip(size=(width, height), color=(60, 20, 80)).set_duration(duration)
        
        clips = [bg]
        
        # Podcast name
        if podcast_name:
            pod_text = TextClip(
                podcast_name,
                fontsize=40,
                color='white'
            ).set_duration(duration).set_position((50, 50))
            clips.append(pod_text)
        
        # Quote
        if quote_text:
            quote = TextClip(
                f'"{quote_text}"',
                fontsize=45,
                color='white',
                method='caption',
                size=(width - 100, None),
                align='center'
            ).set_duration(duration).set_position('center')
            clips.append(quote)
        
        # Speaker
        if speaker:
            speak_text = TextClip(
                f"— {speaker}",
                fontsize=35,
                color='yellow'
            ).set_duration(duration).set_position(('center', height - 150))
            clips.append(speak_text)
        
        # Audio waveform placeholder (would use actual waveform visualization)
        wave_text = TextClip(
            "~ ♪ ♫ ♪ ~",
            fontsize=60,
            color=(200, 100, 200)
        ).set_duration(duration).set_position(('center', height - 250))
        clips.append(wave_text)
        
        video = CompositeVideoClip(clips).set_audio(audio)
        
        output = self._resolve_output(
            f"podcast_clip_{int(datetime.now().timestamp())}.mp4"
        )
        video.write_videofile(str(output), fps=30, codec='libx264', audio_codec='aac')
        video.close()
        audio.close()
        
        return output
    
    def _event_promo(self) -> Path:
        """Generate event promotional video."""
        from moviepy.editor import (ColorClip, TextClip, CompositeVideoClip,
                                   concatenate_videoclips)
        
        event_name = self.data['event_name']
        date = self.data['date']
        location = self.data['location']
        description = self.data['description']
        
        slides = [
            (event_name, 3),
            (f"{date}\n{location}", 3),
            (description, 3),
            ("Save the Date!", 3),
        ]
        
        clips = []
        for text, dur in slides:
            clip = self._create_text_slide(text, dur, bg_color=(80, 40, 40))
            clips.append(clip)
        
        final = concatenate_videoclips(clips, method="compose")
        
        output = self._resolve_output(
            f"event_{event_name.lower().replace(' ', '_')}.mp4"
        )
        final.write_videofile(str(output), fps=30, codec='libx264')
        final.close()
        
        return output
    
    def _announcement(self) -> Path:
        """Generate announcement video."""
        from moviepy.editor import ColorClip, TextClip, CompositeVideoClip
        
        title = self.data['title']
        message = self.data['message']
        duration = self.data.get('duration', 10)
        
        width, height = 1920, 1080
        
        bg = ColorClip(size=(width, height), color=(30, 50, 80)).set_duration(duration)
        
        title_clip = TextClip(
            title,
            fontsize=80,
            color='white',
            font='Arial-Bold'
        ).set_duration(duration).set_position(('center', 200))
        
        message_clip = TextClip(
            message,
            fontsize=45,
            color='white',
            method='caption',
            size=(width - 200, None),
            align='center'
        ).set_duration(duration).set_position('center')
        
        video = CompositeVideoClip([bg, title_clip, message_clip])
        
        output = self._resolve_output(
            f"announcement_{title.lower().replace(' ', '_')}.mp4"
        )
        video.write_videofile(str(output), fps=30, codec='libx264')
        video.close()
        
        return output
    
    def _create_text_slide(self, text: str, duration: float, 
                          bg_color: tuple = (40, 40, 50)) -> Any:
        """Helper to create text slide."""
        from moviepy.editor import ColorClip, TextClip, CompositeVideoClip
        
        width, height = 1920, 1080
        
        bg = ColorClip(size=(width, height), color=bg_color).set_duration(duration)
        
        txt = TextClip(
            text,
            fontsize=60,
            color='white',
            method='caption',
            size=(width - 200, None),
            align='center'
        ).set_duration(duration).set_position('center')
        
        return CompositeVideoClip([bg, txt])
    
    def _add_music_track(self, video, music_source: str, volume: float = 0.3):
        """Add music to video."""
        from moviepy.editor import AudioFileClip, concatenate_audioclips
        from moviepy.audio.fx.all import audio_fadein, audio_fadeout, volumex
        
        music_path = Path(music_source)
        if not music_path.exists():
            raise ValueError(f"Requested music file not found: {music_source}")
        
        music = AudioFileClip(str(music_path))
        
        if music.duration < video.duration:
            loops = int(video.duration / music.duration) + 1
            music = concatenate_audioclips([music] * loops)
        
        music = music.subclip(0, video.duration)
        music = music.fx(volumex, volume)
        music = music.fx(audio_fadein, 1.0).fx(audio_fadeout, 1.0)
        
        return video.set_audio(music)


def list_templates():
    """List available templates."""
    print("Available templates:")
    for name in TemplateEngine.TEMPLATES:
        print(f"  • {name}")


def main():
    parser = argparse.ArgumentParser(description='Generate video from template')
    parser.add_argument('template', nargs='?', help='Template name')
    data_source = parser.add_mutually_exclusive_group()
    data_source.add_argument('--data', '-d', type=Path, help='JSON data file')
    data_source.add_argument('--json', '-j', help='JSON data string')
    parser.add_argument('--list', '-l', action='store_true', help='List templates')
    parser.add_argument('--output', '-o', type=Path, help='Output file')
    
    args = parser.parse_args()
    
    if args.list:
        list_templates()
        return 0
    
    if not args.template:
        print("✗ Please specify a template name or use --list")
        return 1
    
    # Load data
    data = {}
    if args.data:
        with open(args.data) as f:
            data = json.load(f)
    elif args.json:
        data = json.loads(args.json)
    
    try:
        engine = TemplateEngine(args.template, data, output=args.output)
        result = engine.generate()
        print(f"\n🎬 Video ready: {result}")
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
