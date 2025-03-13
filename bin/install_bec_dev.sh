# helper script to (re-)install all BEC dependencies in freshly created virtual environment

# use getops to parse command line arguments; possible arguments are:
# -h: help
# -s: split virtual environment into separate environments for each package
# -c: conda environment name (default: bec_base_env)
# -r: skip installation of redis (default: false)
# -t: skip installation of tmux (default: false)

OPTIND=1

# default values
split_env=false
conda_env_name="bec_base_env"
skip_redis=false
skip_tmux=false


while getopts "hsc:rt" o; do
    case "${o}" in
        h)
            echo "Usage: install_bec_dev.sh [-h] [-s] [-c conda_env_name] [-r] [-t]"
            echo "Options:"
            echo "-h: help"
            echo "-s: split virtual environment into separate environments for each package"
            echo "-c: conda environment name (default: bec_base_env)"
            echo "-r: skip installation of redis (default: false)"
            echo "-t: skip installation of tmux (default: false)"
            return
            ;;
        s)
            split_env=true
            ;;
        c)
            conda_env_name=$OPTARG
            ;;
        r)
            skip_redis=true
            ;;
        t)
            echo "skip tmux"
            skip_tmux=true
            ;;
        \?)
            echo "Invalid option: -$OPTARG" >&2
            return
            ;;
    esac
done

conda_deps=(python=3.11)

# check if tmux should be installed
if [ "$skip_tmux" = false ]; then
    # add tmux to dependencies
    conda_deps+=(tmux)
else
    # check if tmux is installed
    if ! [ "$(which tmux)" ]; then
        echo "tmux is not installed. Please install tmux."
    fi
fi

# check if redis should be installed
if [ "$skip_redis" = false ]; then
    # add redis to dependencies
    conda_deps+=(redis-server)
else
    # check if redis is installed
    if ! [ "$(which redis-server)" ]; then
        echo "redis is not installed. Please install redis."
    fi
fi


# check if conda is installed
if ! [ "$(which conda)" ]; then
    echo "conda is not installed. Please install conda first."
    return
fi

echo "Installing with conda dependencies: ${conda_deps[@]}"

# check if conda environment exists and install it if not
if ! conda env list | grep -q ${conda_env_name}; then
    echo "Creating conda environment ${conda_env_name}..."
    conda create --name ${conda_env_name} ${conda_deps[@]} --channel conda-forge --override-channels
fi
# check if the conda environment has the correct dependencies. If not, install them.
conda activate ${conda_env_name}

dependencies=(pytest_bec_e2e bec_lib bec_ipython_client bec_server)
# split virtual environment into separate environments for each package
if [ "$split_env" = true ]; then
    for package in "${dependencies[@]}"
    do
        echo "Creating virtual environment for $package..."
        cd ./$package
        rm -rf ${package}_venv
        python -m venv ./${package}_venv
        source ./${package}_venv/bin/activate
        pip install -q -q -e '.[dev]'
        cd ../
        deactivate
        echo "Created virtual environment for $package"
    done
    source ./bec_server/bec_server_venv/bin/activate
    return
else # install all packages in one virtual environment
    echo "Creating single virtual environment for all packages..."
    rm -rf ./bec_venv
    python -m venv ./bec_venv
    source ./bec_venv/bin/activate

    for package in "${dependencies[@]}"
    do
        echo "Installing $package..."
        cd ./$package
        pip install -q -q -e '.[dev]'
        cd ../
        echo "Installed $package"
    done
    echo "Created virtual environment for all packages"
fi
