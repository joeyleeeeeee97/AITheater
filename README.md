
# AI Theater: Avalon

This project is a framework for simulating the game of Avalon with AI agents. It generates a complete narrative of the game, including dialogue, and then automatically produces a video with audio and subtitles.

## Features

- **AI-Powered Gameplay:** Uses Large Language Models to simulate the players in the game of Avalon. Each AI agent has a specific role and personality.
- **Dynamic Script Generation:** The game's narrative and dialogue are dynamically generated based on the AI agents' interactions.
- **Automated Video Production:** Automatically generates a video of the gameplay, complete with character avatars, dialogue audio, and subtitles.
- **Customizable Roles and Prompts:** Easily customize the AI agents' roles, personalities, and decision-making processes through prompt engineering.

## How to Run

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure API Keys:**
    - Create a `config.yaml` file from the `config_test.yaml` template.
    - Add your API keys for the desired Large Language Models (e.g., OpenAI, Gemini, Anthropic).

3.  **Run the Game Simulation:**
    ```bash
    python src/main.py
    ```
    This will generate the `final_script.json`, `audio_metadata.json`, and `subtitles.json` files in the `outputs` directory.

4.  **Generate the Video:**
    ```bash
    python tools/video_generator.py outputs/final_script.json outputs/audio_metadata.json outputs/subtitles.json outputs/video.mp4
    ```

## Project Structure

```
├───src/                # Core source code
│   ├───main.py         # Main script to run the game simulation
│   ├───agent.py        # AI agent implementation
│   ├───game_master.py  # Game logic and flow management
│   └───llm_handler.py  # Handles communication with LLMs
├───tools/              # Tools for asset generation
│   ├───video_generator.py # Generates the final video
│   ├───audio_generator.py # Generates audio for the dialogue
│   └───subtitle_generator.py # Generates subtitles
├───prompts/            # Prompts for the AI agents
│   ├───roles/          # Role-specific prompts
│   └───action/         # Action-specific prompts
├───data/               # Game data and configuration
├───outputs/            # Generated output files
└───assets/             # Static assets like fonts and images
```
