# How to Run AI Theater

This document provides instructions on how to run the video generation for the AI Theater project.

## Prerequisites

- Python 3
- A virtual environment is set up in the `.venv` directory.

## Running the Video Generator

1.  **Activate the virtual environment:**
    Before running any scripts, you need to activate the virtual environment.

    ```bash
    source .venv/bin/activate
    ```

2.  **Generate a test video:**
    To generate a short test video (e.g., with 5 events), run the following command:

    ```bash
    python3 generate_precise_video.py --test 5
    ```

3.  **Generate the full video:**
    To generate the complete video, use the `--full` flag:

    ```bash
    python3 generate_precise_video.py --full
    ```
