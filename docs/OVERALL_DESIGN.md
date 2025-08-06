# Overall Design Document: AI Avalon Gameplay Video Generator

## 1. Vision & Goal

The primary goal of this project is to create a fully automated pipeline that transforms a text-based log of an AI-played game of "The Resistance: Avalon" into a compelling, narrated video. This final product is intended to be a piece of AI-generated entertainment, complete with distinct character voices, emotional delivery, and synchronized visual cues, making the strategic gameplay accessible and enjoyable for a viewing audience.

## 2. System Architecture Overview

The system is designed as a sequential, four-stage pipeline. Each stage is a self-contained script that takes the output of the previous stage as its input, ensuring modularity and ease of debugging.

**The pipeline is as follows:**

1.  `game_master.py`: **(Log Generation)** Executes the Avalon game and produces a clean, human-readable text log (`game_output.log`).
2.  `script_writer.py`: **(AI Scriptwriting)** An LLM-powered script that reads the raw game log and transforms it into a structured, detailed JSON "shooting script" (`final_script.json`) with performance instructions.
3.  `audio_generator.py`: **(TTS Narration)** Reads the final script, interprets the performance instructions to generate SSML, and uses a Text-to-Speech (TTS) service to produce individual audio files for each line of dialogue. It also generates a metadata file (`audio_metadata.json`) containing the duration of each audio clip.
4.  `video_generator.py`: **(Video Synthesis)** Acts as the "AI Director," using the final script and audio metadata to composite all assets (background image, audio clips, visual cues) into a final video file (`avalon_game.mp4`).

---

## 3. Detailed Stage Breakdown

### Stage 1: Log Generation

*   **Component**: `game_master.py`
*   **Input**: None (initiates the game).
*   **Core Logic**:
    *   Manages the game flow of Avalon with AI agents.
    *   Uses a dedicated `logging` configuration to output the entire game's events (proposals, discussions, votes, quest results, etc.) in a clean, sequential format.
*   **Output**: `game_output.log` - A plain text file containing the complete, unformatted transcript of the game. This serves as the raw material for the AI Screenwriter.

### Stage 2: AI Scriptwriting (The "AI Director")

*   **Component**: `script_writer.py`
*   **Input**: `game_output.log`
*   **Core Logic**:
    1.  **Read Log**: The script ingests the entire content of `game_output.log`.
    2.  **Prompt Engineering**: A sophisticated prompt is constructed. This prompt instructs a Large Language Model (LLM, specifically Gemini 2.5 Pro) to act as a professional **audio drama director**. The prompt defines a strict JSON output schema.
    3.  **LLM Invocation**: The script sends the raw log and the detailed prompt to the Gemini API.
    4.  **Transformation & Direction**: The LLM processes the linear log and enriches it by:
        *   **Structuring Data**: Converting each line of text into a JSON object with clear keys (e.g., `event_type`, `player_id`, `content`).
        *   **Rewriting Dialogue with Inline Notes**: For each `PLAYER_SPEECH` event, the LLM's primary task is to **rewrite the dialogue** to include **parenthetical, inline performance notes**. These notes guide the emotional delivery, tone, and pacing of the speech directly within the text.
        *   **Example**: The raw line `"I will vote approve"` might be transformed into `"For the sake of getting that clear result, (decisively) I will be voting to approve this team."`
*   **Output**: `final_script.json` - A JSON file containing an array of structured event objects, with dialogue enriched with professional performance notes, ready for the TTS stage.

### Stage 3: TTS Narration

*   **Component**: `audio_generator.py`
*   **Input**: `final_script.json`
*   **Core Logic**:
    1.  **Read Script**: The script parses the `final_script.json` file.
    2.  **Voice Mapping**: A predefined dictionary maps each `player_id` to a specific voice from the chosen TTS service (e.g., Google Cloud TTS, OpenAI TTS).
    3.  **Direct TTS Generation**: The logic is now greatly simplified. For each `PLAYER_SPEECH` event, the script sends the entire `content` string—including the inline performance notes—directly to a high-quality TTS model. Modern TTS models can often interpret these parenthetical notes as contextual hints, influencing their delivery to sound more natural and aligned with the director's intent.
    4.  **API Call**: The text (with notes) is sent to the TTS API.
    5.  **Audio & Metadata Storage**:
        *   The resulting audio is saved as an individual file (e.g., `audio/speech_001.mp3`).
        *   The script calculates the exact duration of the generated audio file. This duration, along with the file path and the original event index, is stored in a new metadata file.
*   **Output**:
    *   A directory (`/audio`) containing all generated speech files.
    *   `audio_metadata.json` - A JSON file mapping each audio file to its duration and corresponding event in the script.

### Stage 4: Video Synthesis (The "AI Director")

*   **Component**: `video_generator.py`
*   **Input**:
    *   `final_script.json`
    *   `audio_metadata.json`
    *   Static assets: `background.png`, visual cue images/templates.
*   **Technology**: **MoviePy** (Python library for video editing).
*   **Core Logic**:
    1.  **Load Assets**: The script loads all necessary inputs into memory.
    2.  **Timeline Construction**: The script iterates through the `final_script.json` and `audio_metadata.json` in order.
    3.  **Clip Generation**: For each `PLAYER_SPEECH` event, it programmatically generates a `CompositeVideoClip`:
        *   An `ImageClip` is created from `background.png` with a duration matching the corresponding audio clip's duration from `audio_metadata.json`.
        *   A visual cue (e.g., a semi-transparent overlay with the player's name and role) is created as another `ImageClip` and overlaid on the background for the same duration. This visually indicates who is speaking.
        *   The corresponding audio file is loaded as an `AudioFileClip`.
        *   The audio is attached to the composite video clip.
    4.  **Concatenation & Rendering**: All generated clips are concatenated in sequence into a single video timeline. The final result is then rendered and saved.
*   **Output**: `avalon_game.mp4` - The final, fully rendered video product.

---

## 4. Key Dependencies

*   **Python 3.9+**
*   **google-generativeai**: For LLM and potentially TTS.
*   **google-cloud-texttospeech**: For advanced SSML-based TTS.
*   **moviepy**: For video synthesis.

This document outlines a clear and robust path to achieving the project's vision. Each component is well-defined, ensuring a smooth and automated workflow from raw game data to a finished entertainment product.
