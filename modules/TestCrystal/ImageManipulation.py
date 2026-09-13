import pathlib
from PIL import Image


class TestCrystalPictures(object):
    def __init__(self, log):
        self.log = log

    def get_images(self, masterfile):
        # returns the visit directory, that of the data collection,
        # the name of the processed dir (different if xrc) and a tag to identify non-rotation datasets

        split_path = masterfile.split("/")

        visit_dir = "/".join(split_path[0:6])
        sub_path = "/".join(split_path[6:])

        diff_image = pathlib.PurePath(visit_dir, "jpegs", sub_path).with_suffix(".jpeg")
        list_of_suffixes = ["_1_0.0.png", "_1_180.0.png", "_1_90.0.png", "_1_270.0.png"]
        prefix = sub_path.split("_master")[0]
        list_of_xtal_pictures = []
        for image_suffix in list_of_suffixes:
            # print(visit_dir, prefix, image_suffix)
            list_of_xtal_pictures.append(f"{visit_dir}/jpegs/{prefix}{image_suffix}")

        return {
            "diff_image": diff_image,
            "xtal_pictures": list_of_xtal_pictures,
            "masterfile": masterfile,
        }

    def create_montage(self, image_paths, output_path):
        """
        Creates a 2x2 montage of images from provided paths.

        Args:
          image_paths: A list of paths to the 4 images.
          output_path: Path to save the montage image.
        """
        images = [Image.open(path) for path in image_paths]
        image_width, image_height = images[0].size

        # Check if all images have the same size
        for image in images:
            if image.width != image_width or image.height != image_height:
                raise ValueError("All images must have the same size")

        rows, cols = 2, 2
        result_width = cols * image_width
        result_height = rows * image_height

        result = Image.new("RGB", (result_width, result_height))

        for i in range(rows):
            for j in range(cols):
                index = i * cols + j
                if index >= len(images):
                    continue
                result.paste(images[index], (j * image_width, i * image_height))

        result.save(output_path)

    def resize_with_aspect_ratio(self, image, new_width):
        """
        Resizes an image to a new width while maintaining its aspect ratio.

        Args:
          image: PIL image
          new_width: The desired width of the resized image.
        """
        width, height = image.size

        # Calculate new height based on the aspect ratio
        new_height = int(height * (new_width / width))

        # Resize the image with the calculated height
        resized_image = image.resize((new_width, new_height))

        return resized_image

    def create_l_montage(self, image_paths, image_below, output_path):
        """
        Creates an L-shape montage (2x2 + 1 image below) from provided paths.

        Args:
          image_paths: A list of paths to the 5 images.
          output_path: Path to save the montage image.
        """
        image_paths
        image_below_path = str(image_below)
        self.log.debug(f"image paths: {image_paths}")

        if len(image_paths) != 4:
            raise ValueError("Expected 4 image paths for L-shape montage")

        images = [Image.open(path) for path in image_paths]
        image_below_pil = Image.open(image_below_path)
        image_width, image_height = images[0].size
        new_image_below = self.resize_with_aspect_ratio(
            image_below_pil, image_width * 2
        )
        image_below_width, image_below_height = new_image_below.size

        # Check if all images have the same size
        for image in images:
            if image.width != image_width or image.height != image_height:
                raise ValueError("All images must have the same size")

        grid_width, grid_height = 2, 2
        result_width = grid_width * image_width
        result_height = (
            grid_height * image_height + image_below_height
        )  # Add height for bottom image

        result = Image.new("RGB", (result_width, result_height))

        for i in range(grid_height):
            for j in range(grid_width):
                index = i * grid_width + j
                if index >= 4:  # Skip last image for grid placement
                    continue
                result.paste(images[index], (j * image_width, i * image_height))

        # Paste the last image below the grid
        result.paste(new_image_below, (0, grid_height * image_height))

        result.save(output_path)
