#!/bin/bash

# Meowrch Automatic Package Update Script
# This script automatically updates packages using the configured AUR helper

LOG_FILE="/var/log/meowrch-auto-update.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

get_aur_helper() {
    if command -v yay &>/dev/null; then
        echo "yay"
    elif command -v paru &>/dev/null; then
        echo "paru"
    else
        log_message "ERROR: No AUR helper found (yay or paru)"
        exit 1
    fi
}

main() {
    log_message "Starting automatic package update"
    
    # Get the AUR helper
    AUR_HELPER=$(get_aur_helper)
    log_message "Using AUR helper: $AUR_HELPER"
    
    # Update package databases
    log_message "Updating package databases..."
    pacman -Sy --noconfirm >> "$LOG_FILE" 2>&1
    
    # Check for updates
    UPDATES=$(checkupdates | wc -l)
    AUR_UPDATES=$($AUR_HELPER -Qua | wc -l)
    
    log_message "Available updates: $UPDATES official, $AUR_UPDATES AUR"
    
    if [ "$UPDATES" -gt 0 ] || [ "$AUR_UPDATES" -gt 0 ]; then
        log_message "Installing updates..."
        # Use the AUR helper to update both official and AUR packages
        $AUR_HELPER -Syu --noconfirm >> "$LOG_FILE" 2>&1
        
        if [ $? -eq 0 ]; then
            log_message "Package update completed successfully"
        else
            log_message "ERROR: Package update failed"
            exit 1
        fi
    else
        log_message "No updates available"
    fi
    
    # Update flatpak packages if flatpak is installed
    if command -v flatpak &>/dev/null; then
        log_message "Updating flatpak packages..."
        flatpak update -y >> "$LOG_FILE" 2>&1
        
        if [ $? -eq 0 ]; then
            log_message "Flatpak update completed successfully"
        else
            log_message "WARNING: Flatpak update failed"
        fi
    fi
    
    log_message "Automatic package update process completed"
}

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Run the main function
main