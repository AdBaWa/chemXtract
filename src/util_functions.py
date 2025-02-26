import base64
from io import BytesIO
from PIL import Image
from langchain_core.prompts.image import ImagePromptTemplate
from langchain_core.prompts import HumanMessagePromptTemplate


def get_mime_type(fmt):
    """Get MIME type for a given image format.

    Args:
        fmt: Image format string (e.g., 'jpeg', 'png').

    Returns:
        MIME type string (e.g., 'image/jpeg').

    Raises:
        ValueError: If the image format is unsupported.
    """
    fmt = fmt.lower()
    if fmt == "jpeg" or fmt == "jpg":
        return "image/jpeg"
    elif fmt == "png":
        return "image/png"
    elif fmt == "ppm":
        return "image/ppm"
    else:
        raise ValueError(f"Unsupported image format for data URL: {fmt}")


def image_bytes_to_base64(image_bytes, dataUrl: bool):
    """Convert image bytes to a base64 data URL string.

    Args:
        image_bytes: Bytes representing an image.

    Returns:
        Base64 data URL string.
    """
    image = Image.open(BytesIO(image_bytes))
    buffered = BytesIO()
    image_format = image.format.upper()
    image.save(buffered, format=image_format)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    mime_type = get_mime_type(image.format)
    data_url_prefix = f"data:{mime_type};base64,"
    if dataUrl:
        return f"{data_url_prefix}{img_str}"
    else:
        return f"{img_str}"


def convert_image_to_base64_from_disk(image_path: str, dataUrl: bool) -> str:
    """
    Converts an image from disk to a base64 data URL.

    Args:
        image_path: The path to the image file.

    Returns:
        A base64 data URL string representing the image.
    """
    try:
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
        return image_bytes_to_base64(image_bytes, dataUrl)
    except FileNotFoundError:
        raise FileNotFoundError(f"Image file not found: {image_path}")
    except Exception as e:
        raise Exception(f"Error converting image to base64: {e}")


def add_file_content_to_messages(messages, image_path: str):
    """
    Adds image content from a local file or a public URL to messages.

    Args:
        messages: List of messages to append to
        image_path: Path to the local image file OR a public image URL

    Returns:
        Updated messages list with the image content added
    """
    if image_path.lower().startswith(("http://", "https://")):  # Check if it's a URL
        image_url = image_path
        url = ImagePromptTemplate().format(url=image_url)  # Format for URL input
        msg = HumanMessagePromptTemplate.from_template(
            template=[
                {"type": "image_url", "image_url": url},
            ]
        )
        messages.append(msg)
    elif image_path.lower().endswith((".png", ".jpg", ".jpeg")):
        try:
            image_base64 = convert_image_to_base64_from_disk(image_path, True)
            url = ImagePromptTemplate().format(url=image_base64)  # Format for base64 input
            msg = HumanMessagePromptTemplate.from_template(
                template=[
                    {"type": "image_url", "image_url": url},
                ]
            )
            messages.append(msg)
        except Exception as e:
            raise Exception(f"Error processing image file {image_path}: {e}")
    else:
        raise ValueError(f"Unsupported input type. Provide a PNG/JPEG file path or a public image URL: {image_path}")

    return messages
