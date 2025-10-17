#!/bin/bash

errors=()
images=()
IFS=$'\n'

workspaceOverlayFolder="$(dirname ${INPUTS_PLUGINS_FILE})"
skipWorkspace=false

INPUTS_CLI_PACKAGE=${INPUTS_CLI_PACKAGE:="@red-hat-developer-hub/cli"} 
# set command names based on CLI package
EXPORT_COMMAND=("plugin" "export")
INPUTS_CONTAINER_BUILD_TOOL=${INPUTS_CONTAINER_BUILD_TOOL:="podman"}
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
    optionalPatch="${workspaceOverlayFolder}/${INPUTS_SOURCE_PATCH_FILE_NAME}"
    if [ -f "${optionalPatch}" ]
    then
        echo "  applying patch on plugin sources"
        patch <${optionalPatch}
    fi

    for plugin in $(cat ${INPUTS_PLUGINS_FILE})
    do
        if [[ "$(echo $plugin | sed 's/ *//')" == "" ]]
        then
            echo "Skip empty line"
            continue
        fi
        if [[ "$(echo $plugin | sed 's/^#.*//')" == "" ]]
        then
            echo "Skip commented line"
            continue
        fi
        pluginPath=$(echo $plugin | sed 's/^\(^[^:]*\): *\(.*\)$/\1/')
        args=$(echo $plugin | sed 's/^\(^[^:]*\): *\(.*\)$/\2/')
        
        pushd $pluginPath > /dev/null
        
        if [[ "$(grep -e '"role" *: *"frontend-plugin' package.json)" != "" ]]
        then
            pluginType=frontend
            optionalScalprumConfigFile="$(dirname ${INPUTS_PLUGINS_FILE})/${pluginPath}/${INPUTS_SCALPRUM_CONFIG_FILE_NAME}"
            if [ -f "${optionalScalprumConfigFile}" ]
            then
                args="$args --scalprum-config ${optionalScalprumConfigFile}"
            fi
        else
            pluginType=backend
        fi
        
        echo "========== Exporting $pluginType plugin $pluginPath =========="
        
        optionalSourceOverlay="$(dirname ${INPUTS_PLUGINS_FILE})/${pluginPath}/${INPUTS_SOURCE_OVERLAY_FOLDER_NAME}"
        if [ -d "${optionalSourceOverlay}" ]
        then
            echo "  copying source overlay"
            cp -Rfv ${optionalSourceOverlay}/* .
        fi

        set +e
        echo "  running the '${INPUTS_CLI_PACKAGE}@${INPUTS_CLI_VERSION} ${EXPORT_COMMAND[@]}' command with args: $args"
        echo "$args" | xargs npx --yes ${INPUTS_CLI_PACKAGE}@${INPUTS_CLI_VERSION} "${EXPORT_COMMAND[@]}"
        if [ $? -ne 0 ]
        then
            errors+=("${pluginPath}")
            set -e
            popd > /dev/null
            continue
        fi

        # package the dynamic plugin in a container image
        if [[ "${INPUTS_IMAGE_REPOSITORY_PREFIX}" != "" ]]
        then
            PLUGIN_NAME=$(jq -r '.name | sub("^@"; "") | sub("[/@]"; "-")' package.json)
            PLUGIN_VERSION="${INPUTS_IMAGE_TAG_PREFIX}$(jq -r '.version' package.json)"
            PLUGIN_CONTAINER_TAG="${INPUTS_IMAGE_REPOSITORY_PREFIX}/${PLUGIN_NAME}:${PLUGIN_VERSION}"

            echo "========== Packaging Container ${PLUGIN_CONTAINER_TAG} =========="
            echo "  running the '${INPUTS_CLI_PACKAGE}@${INPUTS_CLI_VERSION} ${PACKAGE_COMMAND[@]}' command"
            npx --yes ${INPUTS_CLI_PACKAGE}@${INPUTS_CLI_VERSION} "${PACKAGE_COMMAND[@]}" --tag "${PLUGIN_CONTAINER_TAG}"
            if [ $? -eq 0 ] 
            then
                if [[ "${INPUTS_PUSH_CONTAINER_IMAGE}" == "true" ]]
                then
                    echo "========== Publishing Container ${PLUGIN_CONTAINER_TAG} =========="
                    ${INPUTS_CONTAINER_BUILD_TOOL} push $PLUGIN_CONTAINER_TAG
                    if [ $? -eq 0 ] 
                    then
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

        if [[ "${INPUTS_DESTINATION}" != "" ]]
        then
            echo "========== Moving $pluginType plugin $pluginPath archive into ${INPUTS_DESTINATION} =========="

            packDestination=${INPUTS_DESTINATION}
            mkdir -pv ${packDestination}

            echo "  running npm pack on the exported './dist-dynamic' sub-folder"
            json=$(npm pack ./dist-dynamic --pack-destination $packDestination --json)
            if [ $? -ne 0 ]
            then
                errors+=("${pluginPath}")
                set -e
                popd > /dev/null
                continue
            fi
            set -e
            
            filename=$(echo "$json" | jq -r '.[0].filename')
            integrity=$(echo "$json" | jq -r '.[0].integrity')
            echo "$integrity" > $packDestination/${filename}.integrity
            optionalConfigFile="$(dirname ${INPUTS_PLUGINS_FILE})/${pluginPath}/${INPUTS_APP_CONFIG_FILE_NAME}"
            if [ -f "${optionalConfigFile}" ]
            then
                echo "  copying default app-config"
                cp -v "${optionalConfigFile}" "$packDestination/${filename}.${INPUTS_APP_CONFIG_FILE_NAME}"
            fi
        fi
        set -e
        popd > /dev/null
    done
    echo "Plugins with failed exports: $errors"
fi

FAILED_EXPORTS_OUTPUT=${FAILED_EXPORTS_OUTPUT:-"failed-exports-output"}
touch $FAILED_EXPORTS_OUTPUT
for error in "${errors[@]}"
do
    echo "$error" >> $FAILED_EXPORTS_OUTPUT
done

PUBLISHED_EXPORTS_OUTPUT=${PUBLISHED_EXPORTS_OUTPUT:-"published-exports-output"}
touch $PUBLISHED_EXPORTS_OUTPUT
for image in "${images[@]}"
do
    echo "$image" >> $PUBLISHED_EXPORTS_OUTPUT
done

if [[ "$GITHUB_OUTPUT" != "" ]]
then
    echo "FAILED_EXPORTS<<EOF" >> $GITHUB_OUTPUT
    cat $FAILED_EXPORTS_OUTPUT >> $GITHUB_OUTPUT
    echo "EOF" >> $GITHUB_OUTPUT

    echo "PUBLISHED_EXPORTS<<EOF" >> $GITHUB_OUTPUT
    cat $PUBLISHED_EXPORTS_OUTPUT >> $GITHUB_OUTPUT
    echo "EOF" >> $GITHUB_OUTPUT

    if [[ "${skipWorkspace}" == "true" ]]
    then
        echo "WORKSPACE_SKIPPED_UNCHANGED_SINCE=${INPUTS_LAST_PUBLISH_COMMIT}" >> $GITHUB_OUTPUT
    else
        echo "WORKSPACE_SKIPPED_UNCHANGED_SINCE=false" >> $GITHUB_OUTPUT
    fi
else # if not running in GitHub Actions
    echo "FAILED_EXPORTS:"
    cat $FAILED_EXPORTS_OUTPUT
    echo "--------------------------------"
    echo "PUBLISHED_EXPORTS:"
    cat $PUBLISHED_EXPORTS_OUTPUT
    echo "--------------------------------"
fi