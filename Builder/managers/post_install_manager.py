import os
import subprocess
import tempfile
import traceback
import json
from pathlib import Path

from loguru import logger
from packages import CUSTOM


class PostInstallation:
    @staticmethod
    def apply(auto_update_packages: bool = False):
        logger.info("The post-installation configuration is starting...")
        PostInstallation._set_fish_shell()
        PostInstallation._add_to_gamemode_group()
        PostInstallation._set_default_term()
        PostInstallation._ensure_en_us_locale()
        PostInstallation._configure_mewline()
        
        if auto_update_packages:
            PostInstallation._configure_auto_update()
            
        logger.info("The post-installation configuration is complete!")

    @staticmethod
    def _ensure_en_us_locale():
        locale_file = "/etc/locale.gen"
        target_line = "en_US.UTF-8 UTF-8"
        commented_line = f"#{target_line}"
        found = False
        modified = False

        if not os.path.exists(locale_file):
            logger.warning(
                f'Failed to add a locale. Error: file "{locale_file}" not found!'
            )
            return False

        with open(locale_file) as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped == commented_line:
                new_lines.append(target_line + "\n")
                modified = True
                found = True
            elif stripped == target_line:
                new_lines.append(line)
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(target_line + "\n")
            modified = True

        if modified:
            try:
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
                    tmp_file.writelines(new_lines)
                    tmp_path = tmp_file.name

                subprocess.run(["sudo", "cp", tmp_path, locale_file], check=True)
                os.unlink(tmp_path)

                logger.info("Applying locale-gen....")
                subprocess.run(["sudo", "locale-gen"], check=True)
                logger.success(f'Locale "{target_line}" successfully added!')
                return True
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to add a locale. Error: {e}")
                return False
            except Exception:
                logger.warning(f"Failed to add a locale. Error: {traceback.format_exc()}")
        else:
            logger.success(f'Locale "{target_line}" successfully added!')
            return True

    @staticmethod
    def _set_fish_shell() -> None:
        try:
            subprocess.run(["chsh", "-s", "/usr/bin/fish"], check=True)
            logger.success("The shell is changed to fish!")
        except Exception:
            logger.error(f"Error changing shell: {traceback.format_exc()}")

    @staticmethod
    def _add_to_gamemode_group() -> bool:
        if (
            "games" in CUSTOM
            and "gamemode" in CUSTOM["games"]
            and CUSTOM["games"]["gamemode"].selected
        ):
            try:
                username = os.getenv("USER") or os.getenv("LOGNAME")
                subprocess.run(
                    ["sudo", "usermod", "-a", username, "-G", "gamemode"], check=True
                )
                logger.success("The user is added to the gamemode group!")
            except Exception:
                logger.error(
                    f"Error adding user to group for gamemode: {traceback.format_exc()}"
                )

    @staticmethod
    def _set_default_term() -> bool:
        try:
            subprocess.run(
                [
                    "gsettings",
                    "set",
                    "org.cinnamon.desktop.default-applications.terminal",
                    "exec",
                    "kitty",
                ],
                check=True,
            )
            logger.success("The default terminal is set to kitty!")
            return True
        except Exception:
            logger.error(f"Error setting default terminal: {traceback.format_exc()}")
            return False

    @staticmethod
    def _configure_mewline() -> None:
        """Configure mewline after installation"""
        try:
            logger.info("Configuring mewline...")
            
            # Generate the default config
            subprocess.run(["mewline", "--generate-default-config"], check=True)
            logger.success("Generated mewline default config!")
            
            # Update config to add -98 to ignored workspaces
            PostInstallation._update_mewline_config()
            
            # Generate keybindings for Hyprland
            subprocess.run(["mewline", "--create-keybindings"], check=True)
            logger.success("Generated mewline Hyprland keybindings!")
            
            logger.info("Mewline configuration complete! You can edit the config at ~/.config/mewline/config.json")
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"Error configuring mewline: {e}")
        except FileNotFoundError:
            logger.warning("Mewline not found. It may not have been installed properly.")
        except Exception:
            logger.error(f"Unexpected error configuring mewline: {traceback.format_exc()}")

    @staticmethod
    def _update_mewline_config() -> None:
        """Update mewline config.json to add -98 to ignored workspaces"""
        try:
            # Get the home directory and config path
            home_dir = os.path.expanduser("~")
            config_path = Path(home_dir) / ".config" / "mewline" / "config.json"
            
            if not config_path.exists():
                logger.warning("Mewline config.json not found, skipping workspace configuration")
                return
            
            # Read the current config
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Add -98 to ignored workspaces if not already present
            if "modules" in config and "workspaces" in config["modules"]:
                ignored = config["modules"]["workspaces"].get("ignored", [])
                if -98 not in ignored:
                    ignored.append(-98)
                    config["modules"]["workspaces"]["ignored"] = ignored
                    
                    # Write the updated config back
                    with open(config_path, 'w') as f:
                        json.dump(config, f, indent=4)
                    
                    logger.success("Added workspace -98 to mewline ignored list")
                else:
                    logger.info("Workspace -98 already in mewline ignored list")
            else:
                logger.warning("Mewline config structure unexpected, skipping workspace configuration")
                
        except Exception as e:
            logger.warning(f"Error updating mewline config: {e}")

    @staticmethod
    def _configure_auto_update():
        """Configure automatic package updates using systemd timer"""
        try:
            logger.info("Configuring automatic package updates...")
            
            # Copy the auto-update script to system location
            script_source = Path(__file__).parent.parent.parent / "home" / "bin" / "meowrch-auto-update.sh"
            script_dest = Path("/usr/local/bin/meowrch-auto-update.sh")
            
            if script_source.exists():
                subprocess.run(["sudo", "cp", str(script_source), str(script_dest)], check=True)
                subprocess.run(["sudo", "chmod", "+x", str(script_dest)], check=True)
                logger.success("Auto-update script installed to /usr/local/bin/")
            else:
                logger.error("Auto-update script not found in source directory")
                return
            
            # Copy systemd service and timer files
            systemd_source_dir = Path(__file__).parent.parent.parent / "misc" / "systemd"
            service_source = systemd_source_dir / "meowrch-auto-update.service"
            timer_source = systemd_source_dir / "meowrch-auto-update.timer"
            
            systemd_dest_dir = Path("/etc/systemd/system/")
            
            if service_source.exists() and timer_source.exists():
                subprocess.run(["sudo", "cp", str(service_source), str(systemd_dest_dir)], check=True)
                subprocess.run(["sudo", "cp", str(timer_source), str(systemd_dest_dir)], check=True)
                logger.success("Systemd service and timer files installed")
            else:
                logger.error("Systemd service or timer files not found")
                return
            
            # Reload systemd and enable the timer
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", "meowrch-auto-update.timer"], check=True)
            subprocess.run(["sudo", "systemctl", "start", "meowrch-auto-update.timer"], check=True)
            
            logger.success("Automatic package updates configured and enabled!")
            logger.info("Updates will run 5 minutes after boot and then every 24 hours")
            logger.info("Check logs with: sudo journalctl -u meowrch-auto-update.service")
            
        except Exception as e:
            logger.error(f"Failed to configure automatic package updates: {e}")
            logger.error(f"Full error: {traceback.format_exc()}")