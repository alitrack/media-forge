"""MediaForge CLI — content → podcast/video from the command line.

Usage:
    mediaforge podcast --url https://example.com
    mediaforge video --text "$(cat notes.md)"
    mediaforge serve /tmp/output/
"""

import argparse
import sys


def cmd_podcast(args):
    from mediaforge import Ingester, Composer, Synthesizer
    from mediaforge.types import Source, SourceType, ContentStyle

    # Ingest
    ingester = Ingester()
    if args.url:
        result = ingester.ingest([Source(type=SourceType.URL, content=args.url)])
    elif args.text:
        result = ingester.ingest([Source(type=SourceType.TEXT, content=args.text)])
    else:
        print("Error: provide --url or --text", file=sys.stderr)
        return 1

    # Compose
    composer = Composer(model=args.model, api_key=args.api_key, base_url=args.base_url)
    style = getattr(ContentStyle, args.style.upper(), ContentStyle.INTERVIEW)
    script = composer.compose(
        result.content, style=style,
        voice_map={"host": args.host_voice, "expert": args.expert_voice},
    )

    # Synthesize
    synth = Synthesizer(backend=args.tts_backend)
    output = synth.synthesize(script, args.output)
    print(f"Podcast: {output} ({script.segment_count} segments)")
    return 0


def cmd_video(args):
    from mediaforge import Ingester, Composer, Synthesizer
    from mediaforge.render import get_render_engine
    from mediaforge.render.hooks import HookRegistry
    from mediaforge.render.builtin_hooks import watermark_hook, progress_bar_hook, qrcode_hook
    from mediaforge.types import Source, SourceType, ContentStyle, FrameStyle, STYLE_PRESETS, ASPECT_RATIOS

    # Ingest
    ingester = Ingester()
    if args.url:
        result = ingester.ingest([Source(type=SourceType.URL, content=args.url)])
    elif args.text:
        result = ingester.ingest([Source(type=SourceType.TEXT, content=args.text)])
    else:
        print("Error: provide --url or --text", file=sys.stderr)
        return 1

    # Compose
    composer = Composer(model=args.model, api_key=args.api_key, base_url=args.base_url)
    style = getattr(ContentStyle, args.style.upper(), ContentStyle.INTERVIEW)
    script = composer.compose(
        result.content, style=style,
        voice_map={"host": args.host_voice, "expert": args.expert_voice},
    )

    # Synthesize
    audio_path = args.output.replace(".mp4", ".mp3")
    synth = Synthesizer(backend=args.tts_backend)
    synth.synthesize(script, audio_path)

    # Build hook registry from CLI args
    hooks = HookRegistry()
    if getattr(args, "watermark", None):
        hooks.register("post-frame", watermark_hook(args.watermark))
    if getattr(args, "progress_bar", False):
        hooks.register("post-frame", progress_bar_hook())
    if getattr(args, "qrcode", None):
        hooks.register("pre-ffmpeg", qrcode_hook(args.qrcode))

    # Resolve frame style
    frame_style = None
    if getattr(args, "frame_style", None):
        if args.frame_style in STYLE_PRESETS:
            frame_style = STYLE_PRESETS[args.frame_style]
        else:
            # Try JSON parse
            import json
            try:
                frame_style = FrameStyle.from_dict(json.loads(args.frame_style))
            except (json.JSONDecodeError, TypeError):
                print(f"Warning: unknown style '{args.frame_style}', using dark", file=sys.stderr)
                frame_style = STYLE_PRESETS["dark"]
    if getattr(args, "output_preset", None) and frame_style:
        frame_style.aspect_ratio = args.output_preset

    # Render — use engine registry
    engine_kwargs = {}
    if args.render == "hyperframes":
        engine_kwargs["fps"] = args.fps
        if hooks.count() > 0:
            engine_kwargs["hooks"] = hooks
        if frame_style:
            engine_kwargs["style"] = frame_style
    elif args.render == "default":
        engine_kwargs["frame_count"] = args.frames
        if hooks.count() > 0:
            print(
                "Warning: hooks (--watermark/--qrcode/--progress-bar) only work "
                "with --render hyperframes",
                file=sys.stderr,
            )

    engine = get_render_engine(args.render, **engine_kwargs)
    video = engine.render(script, audio_path, args.output)

    info = f"{script.segment_count} segments"
    if args.render == "hyperframes":
        info += f", {args.fps}fps"
        if hooks.count() > 0:
            info += f", {hooks.count()} hooks"
    else:
        info += f", {args.frames} frames"
    print(f"Video: {video} ({info})")
    return 0


def cmd_serve(args):
    from mediaforge.publish import Publisher
    pub = Publisher()
    url = pub.serve_dir(args.directory)
    print(f"Serving at: {url}")
    print("Press Ctrl+C to stop")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="mediaforge",
        description="Content → podcast/video pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    # podcast
    p = sub.add_parser("podcast", help="Generate audio podcast")
    p.add_argument("--url", help="URL to fetch content from")
    p.add_argument("--text", help="Raw text content")
    p.add_argument("--style", default="interview", choices=["interview", "tutorial", "explainer", "debate"])
    p.add_argument("--host-voice", default="xiaoxiao")
    p.add_argument("--expert-voice", default="yunyang")
    p.add_argument("--model", default="")
    p.add_argument("--api-key")
    p.add_argument("--base-url")
    p.add_argument("--tts-backend", default="edge")
    p.add_argument("--output", default="/tmp/podcast.mp3")

    # video
    v = sub.add_parser("video", help="Generate video with visual frames")
    v.add_argument("--url")
    v.add_argument("--text")
    v.add_argument("--style", default="interview")
    v.add_argument("--host-voice", default="xiaoxiao")
    v.add_argument("--expert-voice", default="yunyang")
    v.add_argument("--model", default="")
    v.add_argument("--api-key")
    v.add_argument("--base-url")
    v.add_argument("--tts-backend", default="edge")
    v.add_argument("--render", default="default", choices=["default", "hyperframes"],
                   help="Render engine: default (static) or hyperframes (animated)")
    v.add_argument("--fps", type=int, default=30,
                   help="Frames per second for hyperframes engine (default: 30)")
    v.add_argument("--frames", type=int, default=6,
                   help="Number of static frames for default engine (default: 6)")
    v.add_argument("--watermark", default=None,
                   help="Watermark text overlay on video (hyperframes only)")
    v.add_argument("--qrcode", default=None,
                   help="QR code URL to overlay on video frames (hyperframes only)")
    v.add_argument("--progress-bar", action="store_true", default=False,
                   help="Show animated progress bar (hyperframes only)")
    v.add_argument("--frame-style", default=None,
                   help="Visual style preset for frames: clean, dark, gradient (default: dark)")
    v.add_argument("--output-preset", default=None,
                   choices=["16:9", "1:1", "9:16", "4:3"],
                   help="Aspect ratio for output video (default: from style)")
    v.add_argument("--output", default="/tmp/video.mp4")

    # serve
    s = sub.add_parser("serve", help="Serve directory via cloudflared")
    s.add_argument("directory")

    args = parser.parse_args()
    if args.command == "podcast":
        return cmd_podcast(args)
    elif args.command == "video":
        return cmd_video(args)
    elif args.command == "serve":
        return cmd_serve(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())