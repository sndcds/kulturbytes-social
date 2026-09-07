import httpx


def get_image_url(
    event: dict,
) -> str | None:
    images = event.get(
        "images"
    ) or {}

    main_image = images.get(
        "main"
    )

    if not main_image:
        return None

    return main_image.get(
        "url"
    )


def download_image(
    client: httpx.Client,
    event: dict,
) -> tuple[
    bytes,
    str,
    str,
]:
    image_url = get_image_url(
        event
    )

    if not image_url:
        raise ValueError(
            "Event besitzt kein Hauptbild"
        )

    response = client.get(
        image_url
    )

    response.raise_for_status()

    content_type = (
        response.headers.get(
            "content-type",
            "image/jpeg",
        )
        .split(";")[0]
        .strip()
    )

    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(
        content_type,
        ".jpg",
    )

    image_uuid = (
        event.get("images", {})
        .get("main", {})
        .get("uuid")
        or event["date"]["uuid"]
    )

    filename = (
        f"{image_uuid}"
        f"{extension}"
    )

    return (
        response.content,
        content_type,
        filename,
    )
