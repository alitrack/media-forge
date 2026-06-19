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
    from mediaforge import Ingester, Composer, Synthesizer, Renderer
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
    audio_path = args.output.replace(".mp4", ".mp3")
    synth = Synthesizer(backend=args.tts_backend)
    synth.synthesize(script, audio_path)

    # Render
    renderer = Renderer()
    video = renderer.render(script, audio_path, args.output, frame_count=args.frames)
    print(f"Video: {video} ({args.frames} frames, {script.segment_count} segments)")
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
    v.add_argument("--model", default="deepseek-chat")
    v.add_argument("--api-key")
    v.add_argument("--base-url")
    v.add_argument("--tts-backend", default="edge")
    v.add_argument("--frames", type=int, default=6)
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