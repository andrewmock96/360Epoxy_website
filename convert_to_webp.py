import argparse
from pathlib import Path

from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
except ImportError:
    register_heif_opener = None


SUPPORTED_EXTENSIONS = {".heic", ".heif", ".jpg", ".jpeg", ".png"}


def format_size(size):
    return f"{size / (1024 * 1024):.2f} MB"


def convert_image(source, output, max_size, quality, overwrite):
    if output.exists() and not overwrite:
        print(f"Skipped {source.name}: {output.name} already exists")
        return None

    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)

        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")

        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        save_options = {"method": 6}
        if source.suffix.lower() == ".png" and image.mode == "RGBA":
            save_options["lossless"] = True
        else:
            save_options["quality"] = quality

        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, "WEBP", **save_options)

    source_size = source.stat().st_size
    output_size = output.stat().st_size
    reduction = (1 - output_size / source_size) * 100
    print(
        f"Converted {source.name} -> {output.name}: "
        f"{format_size(source_size)} -> {format_size(output_size)} "
        f"({reduction:.1f}% smaller)"
    )
    return source_size, output_size


def main():
    parser = argparse.ArgumentParser(
        description="Recursively convert website images to optimized WebP files."
    )
    parser.add_argument(
        "input_folder",
        nargs="?",
        type=Path,
        default=Path("static/images"),
        help="Folder containing source images (default: static/images)",
    )
    parser.add_argument(
        "--output-folder",
        type=Path,
        help="Output root that mirrors the input folders (default: beside originals)",
    )
    parser.add_argument("--max-size", type=int, default=2200)
    parser.add_argument("--quality", type=int, default=85)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    input_folder = args.input_folder
    output_folder = args.output_folder or input_folder

    if not input_folder.is_dir():
        parser.error(f"Input folder does not exist: {input_folder}")

    heic_files = [
        path
        for path in input_folder.rglob("*")
        if path.is_file() and path.suffix.lower() in {".heic", ".heif"}
    ]
    if heic_files:
        if register_heif_opener is None:
            parser.error(
                "HEIC files found, but pillow-heif is not installed. "
                "Run: pip install -r requirements.txt"
            )
        register_heif_opener()

    sources = sorted(
        path
        for path in input_folder.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not sources:
        print(f"No supported images found in {input_folder}")
        return

    totals = [
        result
        for source in sources
        if (
            result := convert_image(
                source,
                (
                    source.with_suffix(".webp")
                    if args.output_folder is None
                    else output_folder
                    / source.relative_to(input_folder).with_suffix(".webp")
                ),
                args.max_size,
                args.quality,
                args.overwrite,
            )
        )
    ]

    if totals:
        source_total = sum(source_size for source_size, _ in totals)
        output_total = sum(output_size for _, output_size in totals)
        reduction = (1 - output_total / source_total) * 100
        print(
            f"Done: {len(totals)} images, "
            f"{format_size(source_total)} -> {format_size(output_total)} "
            f"({reduction:.1f}% smaller)"
        )


if __name__ == "__main__":
    main()
