from loguru import logger
from pynput.keyboard import Key, Listener
from settings import Settings, resolve_path
from template_capture import capture_at_cursor

# Hover over the bobber and press F8 to save a template. Press Esc to stop.
# The same thing is available from the Bobber Images tab of the GUI.

size = 50

def main():
  settings = Settings()
  settings.load()
  directory = resolve_path(settings.img_dir)
  logger.info(f"Hover over the bobber and press F8 to capture, Esc to quit. Saving to {directory}")

  def on_release(key):
    if key == Key.f8:
      logger.info(f"Saved {capture_at_cursor(directory, size)}")
    elif key == Key.esc:
      return False

  with Listener(on_release=on_release) as listener:
    listener.join()

main()
