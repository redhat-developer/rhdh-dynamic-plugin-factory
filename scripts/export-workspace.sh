#!/usr/bin/env bash

errors=()
images=()
IFS=$'\n'

workspaceOverlayFolder="$(dirname "${INPUTS_PLUGINS_FILE}")"
skipWorkspace=false

# INPUTS_CLI_VERSION must be set; or fall back to old default INPUTS_JANUS_CLI_VERSION

INPUTS_CLI_PACKAGE=${INPUTS_CLI_PACKAGE:-"@red-hat-developer-hub/cli"} 
# set command names based on CLI package
EXPORT_COMMAND=("plugin" "export")
INPUTS_CONTAINER_BUILD_TOOL=${INPUTS_CONTAINER_BUILD_TOOL:-"podman"}
PACKAGE_COMMAND=("plugin" "package" "--container-tool" "${INPUTS_CONTAINER_BUILD_TOOL}")


##########################################################
# start TODO remove this once fully migrated to rhdh-cli
# fall back to old Janus defaults
if [[ "${INPUTS_JANUS_CLI_VERSION}" ]]
then
    INPUTS_CLI_VERSION="${INPUTS_JANUS_CLI_VERSION}"
fi
# fall back to old janus-idp/cli commands
if [[ "${INPUTS_CLI_PACKAGE}" == "@janus-idp/cli" ]]
then
    EXPORT_COMMAND=("package" "export-dynamic-plugin")
    PACKAGE_COMMAND=("package" "package-dynamic-plugins")
fi
# end TODO remove this once fully migrated to rhdh-cli
##########################################################

# by default, run online with npx --yes installing the cli 
# use a local binary (for airgapped/hermetic use cases) with:
# export INPUTS_CLI_CALLER=/path/to/node_modules/.bin/rhdh-cli
INPUTS_CLI_CALLER=${INPUTS_CLI_CALLER:-"npx --yes ${INPUTS_CLI_PACKAGE}@${INPUTS_CLI_VERSION}"}

# Check local installation first, then fall back to npx --yes (requires network)
run_cli() {
    local cli_args=("$@")
    local cli_bin=()

    # split by spaces into an array so we can execute
    IFS=" " read -r -a cli_bin <<< "$INPUTS_CLI_CALLER"
    IFS=" " read -r -a cli_args_split <<< "${cli_args[@]}"

    # use @ not * to ignore newlines and show array values as a single line
    # shellcheck disable=SC2145
    echo "  > ${cli_bin[@]} ${cli_args_split[@]}"
    # suppress logging unless an error occurs; then dump full log for debugging purposes
    # we WANT cli_args to split by spaces here
    # shellcheck disable=SC2068
    if ! "${cli_bin[@]}" ${cli_args_split[@]} >/tmp/export-dynamic-cli.log 2>&1; then
        echo "Error running CLI: "
		echo "##########################################################"
        cat /tmp/export-dynamic-cli.log
		echo "##########################################################"

        # Search for both types of log files for backwards compatibility
        local yarn_install_logs=("yarn-install.log" "rhdh-cli.yarn-install.log")
        for log_file in "${yarn_install_logs[@]}"; do
            if [[ -f "$log_file" ]]; then
                cat "$log_file"
                echo "##########################################################"
            fi
        done
        return 1
    fi
    rm -f /tmp/export-dynamic-cli.log
    return 0
}

set -e
if [[ "${INPUTS_LAST_PUBLISH_COMMIT}" != "" ]]
then
    pushd "${workspaceOverlayFolder}"  > /dev/null
    workspaceLastCommit="$(git log -1 --format=%H .)"
    echo "Checking if workspace last commit (${workspaceLastCommit}) is an ancestor of the last published commit (${INPUTS_LAST_PUBLISH_COMMIT})"
    if git merge-base --is-ancestor "${workspaceLastCommit}" "${INPUTS_LAST_PUBLISH_COMMIT}"
    then
        skipWorkspace=true
    fi
    popd  > /dev/null
fi

if [[ "${skipWorkspace}" == "true" ]]
then
    echo "Skipping workspace since it didn't change since last published commit (${INPUTS_LAST_PUBLISH_COMMIT})"
else
    if [[ -f "${workspaceOverlayFolder}/backstage.json" ]]
    then
        echo "Overriding backstage.json file before exporting plugins to override the supportedVersions package field."
        if [[ -f "backstage.json" ]]
        then
            cp -fv "backstage.json" "backstage.json.save"
            trap "mv -fv 'backstage.json.save' 'backstage.json'" EXIT
        fi
        cp -fv "${workspaceOverlayFolder}/backstage.json" "backstage.json"
    fi

    # We use '|| [[ -n "$plugin" ]]' to catch the last line even if it lacks a newline.
    while IFS= read -r plugin || [[ -n "$plugin" ]]
    do
        # echo "Processing plugin: $plugin"
        # Skip empty lines
        if [[ -z "${plugin// /}" ]]; then
            echo "Skip empty line"
            continue
        fi
        # Skip commented lines
        # shellcheck disable=SC2001
        if [[ "$(echo "$plugin" | sed 's/^#.*//')" == "" ]]; then
            echo "Skip commented line"
            continue
        fi
        # shellcheck disable=SC2001
        pluginPath=$(echo "$plugin" | sed 's/^\(^[^:]*\): *\(.*\)$/\1/')
        # shellcheck disable=SC2001
        args=$(echo "$plugin" | sed 's/^\(^[^:]*\): *\(.*\)$/\2/')
        
        pushd "$pluginPath" > /dev/null
        
        if [[ "$(grep -e '"role" *: *"frontend-plugin' package.json)" != "" ]]
        then
            pluginType=frontend
            optionalScalprumConfigFile="${workspaceOverlayFolder}/${pluginPath}/${INPUTS_SCALPRUM_CONFIG_FILE_NAME}"
            if [ -f "${optionalScalprumConfigFile}" ]
            then
                args="$args --scalprum-config ${optionalScalprumConfigFile}"
            fi
        else
            pluginType=backend
        fi
        
        echo "========== Exporting $pluginType plugin $pluginPath =========="
        
        optionalSourceOverlay="${workspaceOverlayFolder}/${pluginPath}/${INPUTS_SOURCE_OVERLAY_FOLDER_NAME}"
        if [ -d "${optionalSourceOverlay}" ]
        then
            echo "  copying source overlay"
            cp -Rfv "${optionalSourceOverlay}"/* .
        fi

        set +e
        if ! run_cli "${EXPORT_COMMAND[@]}" "$args"; then
            errors+=("${pluginPath}")
            set -e
            popd > /dev/null
            continue
        fi
        echo

        # package the dynamic plugin in a container image
        if [[ "${INPUTS_IMAGE_REPOSITORY_PREFIX}" != "" ]]
        then
            PLUGIN_NAME=$(jq -r '.name | sub("^@"; "") | sub("[/@]"; "-")' package.json)
            PLUGIN_VERSION="${INPUTS_IMAGE_TAG_PREFIX}$(jq -r '.version' package.json)"
            PLUGIN_CONTAINER_TAG="${INPUTS_IMAGE_REPOSITORY_PREFIX}/${PLUGIN_NAME}:${PLUGIN_VERSION}"

            echo "========== Packaging Container ${PLUGIN_CONTAINER_TAG} =========="
            if run_cli "${PACKAGE_COMMAND[@]}" --tag "${PLUGIN_CONTAINER_TAG}"; then
                if [[ "${INPUTS_PUSH_CONTAINER_IMAGE}" == "true" ]]
                then
                    echo "========== Publishing Container ${PLUGIN_CONTAINER_TAG} =========="
                    if ${INPUTS_CONTAINER_BUILD_TOOL} push "$PLUGIN_CONTAINER_TAG"; then
                        images+=("${PLUGIN_CONTAINER_TAG}")
                    else
                        echo " Error pushing container image"
                        errors+=("${pluginPath}")
                    fi
                else
                        images+=("${PLUGIN_CONTAINER_TAG}")
                fi
            else
                echo " Error building container image"
                errors+=("${pluginPath}")
            fi
        fi
        echo

        if [[ "${INPUTS_DESTINATION}" != "" ]]
        then
            echo "========== Moving $pluginType plugin $pluginPath archive into ${INPUTS_DESTINATION} =========="

            packDestination=${INPUTS_DESTINATION}
            mkdir -pv "${packDestination}"

            echo "  running npm pack on the exported './dist-dynamic' sub-folder"
            if ! json=$(npm pack ./dist-dynamic --pack-destination "$packDestination" --json); then
                errors+=("${pluginPath}")
                set -e
                popd > /dev/null
                continue
            fi
            set -e
            
            filename=$(echo "$json" | jq -r '.[0].filename')
            integrity=$(echo "$json" | jq -r '.[0].integrity')
            echo "$integrity" > "$packDestination/${filename}.integrity"
            optionalConfigFile="${workspaceOverlayFolder}/${pluginPath}/${INPUTS_APP_CONFIG_FILE_NAME}"
            if [ -f "${optionalConfigFile}" ]
            then
                echo "  copying default app-config"
                cp -v "${optionalConfigFile}" "$packDestination/${filename}.${INPUTS_APP_CONFIG_FILE_NAME}"
            fi
        fi
        set -e
        popd > /dev/null
    done < "${INPUTS_PLUGINS_FILE}"
    if [[ ${#errors[@]} -gt 0 ]]; then
        echo "Plugins with failed exports: ${errors[*]}"
    fi
fi

FAILED_EXPORTS_OUTPUT=${FAILED_EXPORTS_OUTPUT:-"failed-exports-output"}
touch "$FAILED_EXPORTS_OUTPUT"
for error in "${errors[@]}"
do
    echo "$error" >> "$FAILED_EXPORTS_OUTPUT"
done

PUBLISHED_EXPORTS_OUTPUT=${PUBLISHED_EXPORTS_OUTPUT:-"published-exports-output"}
touch "$PUBLISHED_EXPORTS_OUTPUT"
for image in "${images[@]}"
do
    echo "$image" >> "$PUBLISHED_EXPORTS_OUTPUT"
done

# write to a temp file if the GITHUB_OUTPUT pipe isn't set
if [[ ! "$GITHUB_OUTPUT" ]]; then GITHUB_OUTPUT=/tmp/github_output.txt; fi

echo "FAILED_EXPORTS<<EOF" | tee -a "$GITHUB_OUTPUT"
tee -a "$GITHUB_OUTPUT" < "$FAILED_EXPORTS_OUTPUT"
echo "EOF" | tee -a "$GITHUB_OUTPUT"

echo "PUBLISHED_EXPORTS<<EOF" | tee -a "$GITHUB_OUTPUT"
tee -a "$GITHUB_OUTPUT" < "$PUBLISHED_EXPORTS_OUTPUT"
echo "EOF" | tee -a "$GITHUB_OUTPUT"

if [[ "${skipWorkspace}" == "true" ]]
then
    echo "WORKSPACE_SKIPPED_UNCHANGED_SINCE=${INPUTS_LAST_PUBLISH_COMMIT}" | tee -a "$GITHUB_OUTPUT"
else
    echo "WORKSPACE_SKIPPED_UNCHANGED_SINCE=false" | tee -a "$GITHUB_OUTPUT"
fi

# exit a return code equivalent to the number of errors
exit $((${#errors[@]}))
