#!/bin/bash
set -e

# Absolute path to the overlay root directory (patches directory will be overlay-root/patches)
OVERLAY_ROOT_DIR="$1" 

# Expected to be "." if CWD is already the target, or an absolute path to cd into
TARGET_APPLY_DIR_ARG="$2"

# Name of the overlay subdirectory (defaults to "overlay" if not provided)
SOURCE_OVERLAY_FOLDER_NAME="${3:-overlay}"

# Construct the patches directory path
PATCHES_SOURCE_DIR="${OVERLAY_ROOT_DIR}/patches"
echo "PATCHES_SOURCE_DIR: ${PATCHES_SOURCE_DIR}"
# Source overlay files are expected directly in the overlay root
SOURCE_OVERLAY_DIR="${OVERLAY_ROOT_DIR}"

echo "=== Override Sources Script ==="
echo "  Overlay root: ${OVERLAY_ROOT_DIR}"
echo "  Source of patches: ${PATCHES_SOURCE_DIR}"
echo "  Source overlay folder: ${SOURCE_OVERLAY_DIR}"
echo "  Overlay subfolder name: ${SOURCE_OVERLAY_FOLDER_NAME}"

EFFECTIVE_TARGET_APPLY_DIR=$(pwd)
PUSHED_DIR=false # Flag to track if we actually changed directory

# Cleanup function to ensure we pop back if a directory was pushed
_cleanup() {
  if [ "$PUSHED_DIR" = true ]
  then
    popd > /dev/null
  fi
}
trap _cleanup EXIT 

if [[ -f "${OVERLAY_ROOT_DIR}/backstage.json" ]]
then
  echo "Overriding backstage.json file"
  cp -fv "${OVERLAY_ROOT_DIR}/backstage.json" "${TARGET_APPLY_DIR_ARG}/backstage.json"
fi

if [[ "${TARGET_APPLY_DIR_ARG}" != "." ]]
then
  if [ ! -d "$TARGET_APPLY_DIR_ARG" ]
  then
    echo "Error: Specified target directory for applying patches ($TARGET_APPLY_DIR_ARG) does not exist."
    exit 1
  fi
  pushd "$TARGET_APPLY_DIR_ARG" > /dev/null
  PUSHED_DIR=true
  echo "  Changed working directory to: $(pwd) for applying patches"
else
  echo "  Applying patches in current working directory: $(pwd)"
fi

PATCHES_APPLIED=0
if [[ -d "$PATCHES_SOURCE_DIR" ]]
then
  # Find and sort .patch files to ensure ordered application
  readarray -t PATCH_FILES < <(find "$PATCHES_SOURCE_DIR" -maxdepth 1 -type f -name "*.patch" | sort)
  
  if [ ${#PATCH_FILES[@]} -gt 0 ]
  then
    echo "Found patch files to apply in $(pwd):"
    printf "  - %s\n" "${PATCH_FILES[@]}"
    
    PATCHES_APPLIED=0
    for patch_file in "${PATCH_FILES[@]}"; do
      echo "Attempting to apply patch: $patch_file"
      if git apply --check "$patch_file"; then
        git apply "$patch_file"
        echo "Successfully applied patch: $patch_file"
        ((++PATCHES_APPLIED))
      else
        echo "Error: Patch $patch_file could not be applied cleanly in $(pwd)." >&2
        exit 1 # Fail if a patch cannot be applied
      fi
    done
    echo "All ${PATCHES_APPLIED} patches applied successfully in $(pwd)."
  else
    echo "No .patch files found in $PATCHES_SOURCE_DIR. Skipping patching."
  fi
else
  echo "Patches directory ($PATCHES_SOURCE_DIR) not found. Skipping patching."
fi

SOURCE_OVERLAY_APPLIED=false
PLUGINS_FILE="${SOURCE_OVERLAY_DIR}/plugins-list.yaml"

if [[ -f "$PLUGINS_FILE" ]]; then
  echo "Found plugins list file: $PLUGINS_FILE"
  plugin_overlays_applied=0
  while IFS= read -r plugin; do

    # Skip empty lines
    if [[ "$(echo $plugin | sed 's/ *//')" == "" ]]; then
      echo "Skip empty line"
      continue
    fi
    
    # Skip commented lines
    if [[ "$(echo $plugin | sed 's/^#.*//')" == "" ]]; then
      echo "Skip commented line"
      continue
    fi
    
    # Extract plugin path (part before colon)
    pluginPath=$(echo $plugin | sed 's/^\([^:]*\): *\(.*\)$/\1/')
    
    echo "Processing plugin: $pluginPath"
    
    if [[ -d "./$pluginPath" ]]; then
      optionalSourceOverlay="${SOURCE_OVERLAY_DIR}/${pluginPath}/${SOURCE_OVERLAY_FOLDER_NAME}"
      
      if [[ -d "$optionalSourceOverlay" ]]; then
        echo "  Found overlay directory: $optionalSourceOverlay"
        echo "  Copying overlay files to: ./$pluginPath"
        
        if cp -Rfv "$optionalSourceOverlay"/* "./$pluginPath"/; then
          overlay_files_copied=$(find "$optionalSourceOverlay" -type f | wc -l)
          echo "    Overlay files copied: $overlay_files_copied"
          ((++plugin_overlays_applied))
          SOURCE_OVERLAY_APPLIED=true
        else
          echo "Error: Failed to copy overlay files from $optionalSourceOverlay" >&2
          exit 1
        fi
      else
        echo "  No overlay directory found at: $optionalSourceOverlay"
      fi
    else
      echo "  Plugin directory './$pluginPath' not found in workspace. Skipping."
    fi
  done < "$PLUGINS_FILE"
  
  if [[ $plugin_overlays_applied -gt 0 ]]; then
    echo "Successfully applied overlays to $plugin_overlays_applied plugin(s)."
  else
    echo "No overlays found for any plugins listed in $PLUGINS_FILE."
  fi
else
  echo "No plugins list file found at $PLUGINS_FILE. Skipping overlay copy."
fi

# Output number of patches applied for GitHub Actions
if [[ "$GITHUB_OUTPUT" != "" ]]; then
  echo "PATCHES_APPLIED=${PATCHES_APPLIED}" >> $GITHUB_OUTPUT
  echo "SOURCE_OVERLAY_APPLIED=${SOURCE_OVERLAY_APPLIED}" >> $GITHUB_OUTPUT
fi

echo "=== Override Sources Script Finished ==="
exit 0