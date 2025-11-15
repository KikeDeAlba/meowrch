import json
import random
import logging
import traceback
import subprocess
from pathlib import Path
from typing import Dict, Optional, Union

from .config import Config
from .other import notify
from .selecting import Selector
from .exceptions import InvalidSession, NoThemesToInstall
from .schemes import Theme
from vars import SESSION_TYPE
from .loader import theme_options


class ThemeManager:
	__slots__ = ('themes', 'current_theme')
	themes: Dict[str, Theme]
	current_theme: Theme

	def __init__(self) -> None:
		self.themes: Dict[str, Theme] = {theme.name: theme for theme in Config.get_all_themes()}

		if len(self.themes) < 1:
			raise NoThemesToInstall()

		if SESSION_TYPE == "x11":
			cur_theme = Config.get_current_xtheme()
		elif SESSION_TYPE == "wayland":
			cur_theme = Config.get_current_wtheme()
		else:
			raise InvalidSession(session=SESSION_TYPE)

		if cur_theme in self.themes:
			self.current_theme = self.themes[cur_theme]
			wallpaper = Config.get_current_wallpaper()
			if wallpaper is None or not Path(wallpaper).exists():
				logging.warning(f"Theme \"{cur_theme}\" does not support the wallpaper set. We set random wallpapers.")
				self.set_random_wallpaper()
		else:
			logging.warning(f"The installed theme \"{cur_theme}\" is not in the list of themes in the config")
			self.set_random_theme()


	def set_theme(self, theme: Union[str, Theme]) -> None:
		##==> Проверка входящих данных
		##########################################
		if isinstance(theme, str):
			logging.debug(f"The process of installing the \"{theme}\" theme has begun")
			obj: Optional[Theme] = self.themes.get(theme, None)

			if obj is None:
				logging.error(f"[X] Theme named \"{theme.name}\" not found")
				return

			theme = obj

		elif isinstance(theme, Theme):
			logging.debug(f"The process of installing the \"{theme.name}\" theme has begun")
			
		##==> Применение темы
		##########################################
		for option in theme_options:
			try:
				option.apply(theme.name)
			except:
				logging.error(f"[X] Unknown error when applying the \"{option._id}\" config: {traceback.format_exc()}")

		self.current_theme = theme
		Config._set_theme(theme_name=theme.name)

		##==> Устанавливаем подходящие обои
		##########################################
		current_wallpaper = Config.get_current_wallpaper()
		if current_wallpaper is None or not Path(current_wallpaper).exists():
			self.set_random_wallpaper()
		else:
			if current_wallpaper not in [str(i) for i in self.current_theme.available_wallpapers]:
				self.set_random_wallpaper()

		logging.debug(f"The theme has been successfully installed: {theme.name}")

	def set_current_theme(self) -> None:
		logging.debug("The process of setting a current theme has begun")
		self.set_theme(self.current_theme)

	def set_random_theme(self) -> None:
		logging.debug("The process of setting a random theme has begun")
		th = list(self.themes.values())

		if len(th) < 1:
			notify("Critical error!", f"There are no themes available to install for session \"{SESSION_TYPE}\"")
			raise NoThemesToInstall()

		random_theme: Theme = random.choice(list(self.themes.values()))
		self.set_theme(random_theme.name)

	def select_theme(self):
		logging.debug("The process of selecting theme using the rofi menu has begun")

		try:
			theme = Selector.select_theme(list(self.themes.values()))
		except:
			logging.error(f"An error occurred while selecting theme using rofi: {traceback.format_exc()}")
			return

		if theme is not None:
			self.set_theme(theme)

	def add_wallpaper_to_theme(self, wallpaper: Union[str, Path], theme_name: Optional[str] = None) -> bool:
		"""
		Adds a new wallpaper to the specified theme's available wallpapers list.
		
		Args:
			wallpaper: Path to the wallpaper file to add
			theme_name: Name of the theme to add wallpaper to. If None, uses current theme.
			
		Returns:
			bool: True if wallpaper was added successfully, False otherwise
		"""
		if theme_name is None:
			theme_name = self.current_theme.name
			
		wallpaper_path = Path(wallpaper).expanduser().resolve()
		
		# Validate wallpaper exists
		if not wallpaper_path.exists():
			logging.error(f"Wallpaper file does not exist: {wallpaper_path}")
			notify("Error", f"Wallpaper file not found: {wallpaper_path}", critical=True)
			return False
			
		# Validate it's an image file
		valid_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}
		if wallpaper_path.suffix.lower() not in valid_extensions:
			logging.error(f"Invalid wallpaper file format: {wallpaper_path.suffix}")
			notify("Error", f"Invalid image format: {wallpaper_path.suffix}", critical=True)
			return False
		
		# Check if theme exists
		if theme_name not in self.themes:
			logging.error(f"Theme '{theme_name}' not found")
			notify("Error", f"Theme '{theme_name}' not found", critical=True)
			return False
			
		theme = self.themes[theme_name]
		
		# Check if wallpaper is already in the theme
		if wallpaper_path in theme.available_wallpapers:
			logging.warning(f"Wallpaper already exists in theme '{theme_name}': {wallpaper_path}")
			notify("Info", f"Wallpaper already in theme '{theme_name}'")
			return True
			
		# Add wallpaper to theme's available wallpapers
		theme.available_wallpapers.append(wallpaper_path)
		
		# Convert path to use ~ notation for config storage
		home_path = Path.home()
		try:
			# If the path is under home directory, use ~ notation
			relative_path = wallpaper_path.relative_to(home_path)
			config_path = f"~/{relative_path}"
		except ValueError:
			# If not under home directory, use absolute path
			config_path = str(wallpaper_path)
		
		# Update config file
		try:
			Config._add_wallpaper_to_theme(theme_name, config_path)
			logging.info(f"Successfully added wallpaper to theme '{theme_name}': {wallpaper_path}")
			notify("Success", f"Wallpaper added to theme '{theme_name}'")
			return True
		except Exception:
			logging.error(f"Failed to update config: {traceback.format_exc()}")
			# Rollback the change
			theme.available_wallpapers.remove(wallpaper_path)
			notify("Error", "Failed to update configuration", critical=True)
			return False

	def remove_wallpaper_from_theme(self, wallpaper: Union[str, Path], theme_name: Optional[str] = None) -> bool:
		"""
		Removes a wallpaper from the specified theme's available wallpapers list.
		
		Args:
			wallpaper: Path to the wallpaper file to remove
			theme_name: Name of the theme to remove wallpaper from. If None, uses current theme.
			
		Returns:
			bool: True if wallpaper was removed successfully, False otherwise
		"""
		from vars import WALLPAPERS_CACHE_DIR
		
		if theme_name is None:
			theme_name = self.current_theme.name
			
		wallpaper_path = Path(wallpaper).expanduser().resolve()
		
		# Check if theme exists
		if theme_name not in self.themes:
			logging.error(f"Theme '{theme_name}' not found")
			notify("Error", f"Theme '{theme_name}' not found", critical=True)
			return False
			
		theme = self.themes[theme_name]
		
		# Check if wallpaper exists in the theme
		if wallpaper_path not in theme.available_wallpapers:
			logging.warning(f"Wallpaper not found in theme '{theme_name}': {wallpaper_path}")
			notify("Warning", f"Wallpaper not found in theme '{theme_name}'")
			return False
		
		# Check if it's the last wallpaper in the theme
		if len(theme.available_wallpapers) <= 1:
			logging.warning(f"Cannot remove the last wallpaper from theme '{theme_name}'")
			notify("Warning", "Cannot remove the last wallpaper from theme", critical=True)
			return False
			
		# Remove wallpaper from theme's available wallpapers
		theme.available_wallpapers.remove(wallpaper_path)
		
		# Remove cached thumbnail
		try:
			cache_thumbnail = WALLPAPERS_CACHE_DIR / f"{wallpaper_path.stem}.png"
			if cache_thumbnail.exists():
				cache_thumbnail.unlink()
				logging.debug(f"Removed cached thumbnail: {cache_thumbnail}")
		except Exception:
			logging.warning(f"Failed to remove cached thumbnail: {traceback.format_exc()}")
		
		# Convert path to use ~ notation for config storage
		home_path = Path.home()
		try:
			# If the path is under home directory, use ~ notation
			relative_path = wallpaper_path.relative_to(home_path)
			config_path = f"~/{relative_path}"
		except ValueError:
			# If not under home directory, use absolute path
			config_path = str(wallpaper_path)
		
		# Update config file
		try:
			Config._remove_wallpaper_from_theme(theme_name, config_path)
			logging.info(f"Successfully removed wallpaper from theme '{theme_name}': {wallpaper_path}")
			notify("Success", f"Wallpaper removed from theme '{theme_name}'")
			
			# If the removed wallpaper was the current one, set a random one
			current_wallpaper = Config.get_current_wallpaper()
			if current_wallpaper and Path(current_wallpaper).resolve() == wallpaper_path:
				self.set_random_wallpaper()
				
			return True
		except Exception:
			logging.error(f"Failed to update config: {traceback.format_exc()}")
			# Rollback the change
			theme.available_wallpapers.append(wallpaper_path)
			notify("Error", "Failed to update configuration", critical=True)
			return False

	def _handle_add_wallpaper(self) -> None:
		"""
		Handles the process of adding a new wallpaper to the current theme.
		Opens file dialog, validates the selection, copies to wallpapers folder, adds to theme, and sets it.
		"""
		logging.debug("Starting add wallpaper process")
		
		# Get the wallpaper file from user
		wallpaper_file = Selector.select_wallpaper_file()
		
		if wallpaper_file is None:
			logging.debug("No wallpaper file selected")
			return
		
		# Copy wallpaper to wallpapers folder and add to theme
		copied_wallpaper = self._copy_wallpaper_to_folder(wallpaper_file)
		
		if copied_wallpaper is None:
			return
			
		# Add the wallpaper to the current theme
		if self.add_wallpaper_to_theme(copied_wallpaper):
			# Automatically set the new wallpaper and close the menu
			self.set_wallpaper(copied_wallpaper)
			logging.info(f"Added and set new wallpaper: {copied_wallpaper}")
			notify("Success", f"Wallpaper added and applied: {copied_wallpaper.name}")
		else:
			logging.error(f"Failed to add wallpaper to theme: {copied_wallpaper}")

	def set_wallpaper(self, wallpaper: Path) -> None:
		logging.debug(f"The process of setting a wallpaper \"{wallpaper}\" has begun")
		
		if SESSION_TYPE == "wayland":
			transition_fps = 60
			cursor_pos = "0,0"
			
			try:
				output = subprocess.check_output(
					['wlr-randr', '--json'],
					stderr=subprocess.DEVNULL, 
					universal_newlines=True,
				)
				for output_info in json.loads(output):
					for mode in output_info['modes']:
						if mode.get('current'):
							transition_fps = int(round(mode['refresh']))
							break
					else:
						continue
					break
			except Exception:
				logging.warning(f"Couldn't get the screen frequency using wlr-randr: {traceback.format_exc()}")

			try:
				output = subprocess.check_output(
					['hyprctl', 'cursorpos'],
					 universal_newlines=True,
				).strip()

				if output:
					cursor_pos = output
			except Exception:
				logging.warning(f"Couldn't get the cursor position: {traceback.format_exc()}")

			try:
				subprocess.run([
					'swww', 'img', str(wallpaper),
					'--transition-bezier', '.43,1.19,1,.4',
					'--transition-type', 'grow',
					'--transition-duration', '0.4',
					'--transition-fps', str(transition_fps),
					'--invert-y',
					'--transition-pos', cursor_pos
				], check=True)
			except Exception:
				logging.error(f"Unknown error when installing wallpaper (swww): {traceback.format_exc()}")
				return

		elif SESSION_TYPE == "x11":
			try:
				subprocess.run(['feh', '--no-fehbg', '--bg-fill', str(wallpaper)], check=True)
			except Exception:
				logging.error(f"Unknown error when installing wallpaper (feh): {traceback.format_exc()}")
				return
		else:
			logging.error(f"Unsupported XDG_SESSION_TYPE: {SESSION_TYPE}")
			return

		Config._set_wallpaper(wallpaper)
		logging.debug("The process of selecting a wallpaper has finished")
	
	def _copy_wallpaper_to_folder(self, source_wallpaper: Path) -> Optional[Path]:
		"""
		Copy wallpaper to the meowrch wallpapers folder.
		
		Args:
			source_wallpaper: Path to the source wallpaper file
			
		Returns:
			Optional[Path]: Path to the copied wallpaper in wallpapers folder, or None if failed
		"""
		from vars import MEOWRCH_DIR
		import shutil
		
		wallpapers_dir = MEOWRCH_DIR / "wallpapers"
		wallpapers_dir.mkdir(exist_ok=True)
		
		source_path = Path(source_wallpaper).expanduser().resolve()
		
		# Validate source wallpaper exists
		if not source_path.exists():
			logging.error(f"Source wallpaper file does not exist: {source_path}")
			notify("Error", f"Wallpaper file not found: {source_path}", critical=True)
			return None
			
		# Validate it's an image file
		valid_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}
		if source_path.suffix.lower() not in valid_extensions:
			logging.error(f"Invalid wallpaper file format: {source_path.suffix}")
			notify("Error", f"Invalid image format: {source_path.suffix}", critical=True)
			return None
		
		# Create destination path
		destination_path = wallpapers_dir / source_path.name
		
		# If file with same name exists, add number suffix
		counter = 1
		original_destination = destination_path
		while destination_path.exists():
			stem = original_destination.stem
			suffix = original_destination.suffix
			destination_path = wallpapers_dir / f"{stem}_{counter}{suffix}"
			counter += 1
		
		try:
			# Copy the file
			shutil.copy2(source_path, destination_path)
			logging.info(f"Copied wallpaper from {source_path} to {destination_path}")
			notify("Success", f"Wallpaper copied to: {destination_path.name}")
			return destination_path
			
		except Exception as e:
			logging.error(f"Failed to copy wallpaper: {e}")
			notify("Error", f"Failed to copy wallpaper: {e}", critical=True)
			return None

	def set_current_wallpaper(self) -> None:
		logging.debug("The process of setting a current wallpaper has begun")
		wallpaper = Config.get_current_wallpaper()

		if wallpaper is not None and wallpaper in [str(wp) for wp in self.current_theme.available_wallpapers]:
			wallpaper = Path(wallpaper)
			if wallpaper.exists():
				self.set_wallpaper(wallpaper)
				return
				
		self.set_random_wallpaper()
		logging.debug("The process of setting a current wallpaper has finished")

	def set_random_wallpaper(self) -> None:
		wallpaper = random.choice(self.current_theme.available_wallpapers)

		if wallpaper:
			self.set_wallpaper(wallpaper)
			return

		logging.error("There are no wallpapers available...")
		notify(f"There are no wallpapers available for \"{self.current_theme.name}\"...", critical=True)

	def select_wallpaper(self):
		logging.debug("The process of selecting wallpapers using the rofi menu has begun")

		try:
			result = Selector.select_wallpaper(self.current_theme)
		except:
			logging.error(f"An error occurred while selecting wallpapers using rofi: {traceback.format_exc()}")
			return

		if result is not None:
			if isinstance(result, tuple) and result[0] == "REMOVE_WALLPAPER":
				# Handle removing a wallpaper
				wallpaper_to_remove = result[1]
				if self.remove_wallpaper_from_theme(wallpaper_to_remove):
					logging.info(f"Removed wallpaper: {wallpaper_to_remove}")
					# Continue the selection process to show updated list
					self.select_wallpaper()
				return
			elif result == "ADD_WALLPAPER":
				# Handle adding a new wallpaper (this will set it and close the menu)
				self._handle_add_wallpaper()
				return  # Return immediately to close the menu
			else:
				self.set_wallpaper(result)
