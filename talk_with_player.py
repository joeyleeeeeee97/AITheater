import sys
import os
import json
import google.generativeai as genai

def talk_with_player(player_id: str):
    """
    Starts an interactive chat session with a player agent from a completed game.
    """
    # 1. Load the saved game context
    try:
        with open("game_context.json", 'r') as f:
            all_contexts = json.load(f)
    except FileNotFoundError:
        print("Error: game_context.json not found. Please run the game first.")
        return

    # 2. Find the specific player's context
    player_context = all_contexts.get(player_id)
    if not player_context:
        print(f"Error: Player '{player_id}' not found in game_context.json.")
        print("Available players:", list(all_contexts.keys()))
        return

    # 3. Configure the Gemini client
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        return
    genai.configure(api_key=api_key)

    # 4. Initialize the model and load the history
    print(f"\n--- Starting interview with {player_id} (Role: {player_context['role']}) ---")
    print("The agent's memory is loaded from the game. Ask it anything.")
    print("Type 'exit' or 'quit' to end the interview.")
    
    model = genai.GenerativeModel('models/gemini-2.5-pro')
    chat = model.start_chat(history=player_context['history'])

    # 5. Start the interactive chat loop
    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ['exit', 'quit']:
                print(f"--- End of interview with {player_id} ---")
                break
            
            response = chat.send_message(user_input)
            print(f"\n{player_id}: {response.text}")

        except KeyboardInterrupt:
            print(f"\n--- End of interview with {player_id} ---")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            break

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 talk_with_player.py <player_id>")
        print("Example: python3 talk_with_player.py player_0")
    else:
        talk_with_player(sys.argv[1])
