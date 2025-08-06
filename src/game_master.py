import sys
import os
import logging
import asyncio
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Logging Setup ---
# Generate a unique timestamp for this game run
game_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
output_dir = "outputs"
os.makedirs(output_dir, exist_ok=True) # Ensure the output directory exists

log_filename = os.path.join(output_dir, f"game_output_{game_timestamp}.log")
debug_log_filename = os.path.join(output_dir, f"game_master_debug_{game_timestamp}.log")

# Plain formatter for game_output.log and console
plain_formatter = logging.Formatter('%(message)s')
# Detailed formatter for debug log
debug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')

# Logger for the main game flow (game_output.log and console)
game_logger = logging.getLogger("game_flow")
game_logger.setLevel(logging.INFO)
# Prevent passing messages to the root logger
game_logger.propagate = False

# File handler for the clean game output
game_file_handler = logging.FileHandler(log_filename, mode='w')
game_file_handler.setFormatter(plain_formatter)
game_logger.addHandler(game_file_handler)

# Console handler for the clean game output
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(plain_formatter)
game_logger.addHandler(console_handler)

# Logger for detailed debug messages (game_master_debug.log)
debug_logger = logging.getLogger("debug")
debug_logger.setLevel(logging.DEBUG)
debug_logger.propagate = False

# File handler for the debug log
debug_file_handler = logging.FileHandler(debug_log_filename, mode='w')
debug_file_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_file_handler)
import yaml

# --- End Logging Setup ---

from typing import List
from src.agent import RoleAgent, UnifiedLLMClient, MockLLMClient, BaseMessage, MessageType, GameStartPayload, ActionRequest
import json
import random

class GameMaster:
    """Manages the overall Avalon game flow."""

    def __init__(self, num_players: int = 7):
        self.num_players = num_players
        self.game_id = "avalon_game_001"
        self.agents: List[RoleAgent] = []
        self.game_history: List[BaseMessage] = []
        
        self.quest_num = 0
        self.good_quests_succeeded = 0
        self.evil_quests_failed = 0
        self.team_proposal_reasoning = "" # Initialize team proposal reasoning
        
        try:
            with open("config.yaml", 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            game_logger.info("CRITICAL: config.yaml not found. Using default settings.")
            self.config = {"player_setup": [{"player_id": i, "model": "mock"} for i in range(num_players)]}
        
        self._initialize_agents()

    def _initialize_agents(self):
        player_configs = self.config.get("player_setup", [])
        
        for i in range(self.num_players):
            player_config = next((p for p in player_configs if p['player_id'] == i), None)
            
            if not player_config or player_config.get("model") == "mock":
                # Use MockLLMClient if no config or if model is 'mock'
                llm_client_factory = lambda system_prompt: MockLLMClient(model="mock", system_prompt=system_prompt)
            else:
                # Use UnifiedLLMClient for real models
                model_name = player_config['model']
                llm_client_factory = lambda system_prompt: UnifiedLLMClient(model=model_name, system_prompt=system_prompt)

            self.agents.append(RoleAgent(i, llm_client_factory))

    def _generate_known_info(self, player_id: int, role: str, roles: List[str]) -> str:
        """Generates the known_info string for a player based on their role."""
        evil_roles = {"Mordred", "Morgana", "Minion"} # Oberon is not known to other evil players
        
        if role in evil_roles:
            evil_teammates = [i for i, r in enumerate(roles) if r in evil_roles and i != player_id]
            return f"You are a Minion of Mordred. Your fellow teammates are players {evil_teammates}. You know they are evil, but you don't know their specific roles."
        
        if role == "Merlin":
            # Merlin sees all evil players except for Mordred.
            visible_evil_roles = {"Morgana", "Minion", "Oberon"}
            visible_evil_players = [i for i, r in enumerate(roles) if r in visible_evil_roles]
            
            mordred_in_game = "Mordred" in roles
            
            info_str = f"You see evil in the hearts of players {visible_evil_players}."
            if mordred_in_game:
                info_str += " Be warned, the traitor Mordred is hidden from your sight and walks among them."
            
            return info_str

        if role == "Percival":
            merlin_id = -1
            morgana_id = -1
            for i, r in enumerate(roles):
                if r == "Merlin":
                    merlin_id = i
                elif r == "Morgana":
                    morgana_id = i
            
            if merlin_id != -1 and morgana_id != -1:
                seen_players = random.sample([merlin_id, morgana_id], 2)
                return f"You see players {seen_players}. One is Merlin, and one is Morgana, but you do not know which is which."
        
        return "You have no special knowledge."

    async def run_game(self):
        game_logger.info("--- Game Start ---")
        await self._start_game()

        while self.quest_num < 5 and not self._check_game_end_condition():
            self.quest_num += 1
            game_logger.info(f"\n--- Starting Quest {self.quest_num} ---")
            # Call the new team building phase
            await self._run_team_building_phase()
            await self._run_quest_execution_phase()

        await self._finalize_game()
        await self._run_mvp_phase()

    async def _run_team_building_phase(self):
        team_approved_for_quest = False
        self.consecutive_rejections = 0

        while not team_approved_for_quest:
            game_logger.info(f"\n--- Team Building Attempt (Leader: Player {self.quest_leader_id}) ---")
            # This will be the new combined discussion and proposal phase
            await self._run_discussion_and_proposal_phase()
            await self._run_voting_phase() # This sets self.team_approved

            if self.team_approved:
                team_approved_for_quest = True
                self.consecutive_rejections = 0
            else:
                self.consecutive_rejections += 1
                game_logger.info(f"Team rejected. Consecutive rejections: {self.consecutive_rejections}. Passing leadership.")
                self.quest_leader_id = (self.quest_leader_id + 1) % self.num_players
                if self.consecutive_rejections >= 5:
                    game_logger.info("Five consecutive team rejections. Team is automatically approved.")
                    self.team_approved = True
                    team_approved_for_quest = True
                    self.consecutive_rejections = 0
        return self.team_approved

    async def _finalize_game(self):
        """Announces the primary game result before moving to the MVP phase."""
        game_logger.info("\n--- Game Over ---")
        if self.good_quests_succeeded >= 3:
            # This path will lead to the assassination phase
            await self._run_assassination_phase()
        elif self.evil_quests_failed >= 3:
            game_logger.info("Three quests have failed. Evil wins the game!")
        else:
            # This case should ideally not be reached in a standard game
            game_logger.info("The game has concluded without a clear win condition being met.")

    async def _run_mvp_phase(self):
        """Runs the post-game MVP selection phase."""
        game_logger.info("\n--- MVP Selection Phase ---")
        
        # Announce all roles first
        game_logger.info("The roles for this game were:")
        for agent in self.agents:
            game_logger.info(f"Player {agent.player_id}: {agent.role}")

        # 1. Get MVP statements from each player
        game_logger.info("\n--- MVP Statements ---")
        mvp_statements = {}
        for agent in self.agents:
            action_request = ActionRequest(
                action_type="NOMINATE_MVP",
                description="The game is over. Please state who you think was the MVP and why.",
                available_options=[str(p.player_id) for p in self.agents],
                constraints={}
                # No history segment needed as the agent uses its internal memory
            )
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            response = await agent.receive_message(request_message)
            
            statement = response.payload.action_data.statement
            mvp_statements[agent.player_id] = statement
            game_logger.info(f"Player {agent.player_id} ({agent.role}) says: {statement}")

        # 2. Collect MVP votes
        game_logger.info("\n--- MVP Voting ---")
        mvp_votes = {}
        for agent in self.agents:
             # In a real implementation, you might ask the agent again for a vote
             # For now, we'll just log a placeholder or have a simpler mechanism
             # Let's assume they vote for someone based on their statement (or randomly for now)
             # This part can be expanded with another LLM call if needed.
             # For simplicity, we'll make a simple choice here.
            possible_targets = [p.player_id for p in self.agents if p.player_id != agent.player_id]
            voted_for = random.choice(possible_targets)
            mvp_votes[agent.player_id] = voted_for
            game_logger.info(f"Player {agent.player_id} votes for Player {voted_for} as MVP.")

        # 3. Tally votes and announce MVP
        vote_counts = {}
        for vote in mvp_votes.values():
            vote_counts[vote] = vote_counts.get(vote, 0) + 1
        
        if not vote_counts:
            game_logger.info("No votes were cast for MVP.")
            return

        mvp_player_id = max(vote_counts, key=vote_counts.get)
        game_logger.info("\n--- MVP Result ---")
        game_logger.info(f"The MVP of the game is Player {mvp_player_id} with {vote_counts[mvp_player_id]} votes!")

    async def _run_assassination_phase(self):
        debug_logger.debug("--- Assassination Phase ---")
        
        assassin_agent = None
        merlin_agent = None
        evil_teammates = []

        for agent in self.agents:
            if agent.role == "Minion":
                assassin_agent = agent
            if agent.role == "Merlin":
                merlin_agent = agent
            # Oberon does not participate in the discussion
            if agent.role in self.evil_roles_in_game and agent.role not in ["Minion", "Oberon"]:
                evil_teammates.append(agent)

        if not merlin_agent:
            game_logger.info("Error: Merlin not found. Good wins.")
            return
        
        if not assassin_agent:
            game_logger.info("No Minion found for assassination. Good wins.")
            return

        # --- Step 1: Assassin's Proposal ---
        game_logger.info(f"\n--- The Final Assassination ---")
        game_logger.info(f"The Minion (Player {assassin_agent.player_id}) will now propose a target.")
        
        history_segment = self._get_formatted_history_segment(assassin_agent.known_history_index)
        available_targets = [str(a.player_id) for a in self.agents if a.player_id != assassin_agent.player_id]
        
        action_request = ActionRequest(action_type="ASSASSINATE_PROPOSAL", description="Propose a target to assassinate.", available_options=available_targets, constraints={}, history_segment=history_segment)
        request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{assassin_agent.player_id}", payload=action_request)
        response = await assassin_agent.receive_message(request_message)
        
        proposal_target = response.payload.action_data.target_player
        proposal_reasoning = response.payload.action_data.reasoning
        
        proposal_message = BaseMessage(msg_type=MessageType.GAME_UPDATE, sender_id="GM", recipient_id="ALL", payload={
            "update_type": "ASSASSINATION_PROPOSAL", "assassin_id": assassin_agent.player_id,
            "target_id": proposal_target, "reasoning": proposal_reasoning
        })
        self.game_history.append(proposal_message)
        assassin_agent.known_history_index = len(self.game_history)
        game_logger.info(f"The Minion proposes to assassinate Player {proposal_target}. Reasoning: {proposal_reasoning}")

        # --- Step 2: Evil Team Discussion ---
        if evil_teammates:
            game_logger.info("\nThe evil team will now discuss the proposal...")
            for teammate in evil_teammates:
                history_segment = self._get_formatted_history_segment(teammate.known_history_index)
                action_request = ActionRequest(action_type="ASSASSINATE_DISCUSSION", description="Provide your counsel on the assassination target.", available_options=[], 
                                               constraints={"proposal_target": proposal_target, "proposal_reasoning": proposal_reasoning}, 
                                               history_segment=history_segment)
                request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{teammate.player_id}", payload=action_request)
                response = await teammate.receive_message(request_message)
                
                statement = response.payload.action_data.statement
                discussion_message = BaseMessage(msg_type=MessageType.GAME_UPDATE, sender_id="GM", recipient_id="ALL", payload={
                    "update_type": "ASSASSINATION_DISCUSSION", "player_id": teammate.player_id, "statement": statement
                })
                self.game_history.append(discussion_message)
                teammate.known_history_index = len(self.game_history)
                game_logger.info(f"Player {teammate.player_id} ({teammate.role}) says: {statement}")

        # --- Step 3: Assassin's Final Decision ---
        game_logger.info(f"\nThe Minion (Player {assassin_agent.player_id}) will now make the final decision.")
        history_segment = self._get_formatted_history_segment(assassin_agent.known_history_index)
        action_request = ActionRequest(action_type="ASSASSINATE_DECISION", description="Make your final decision based on the discussion.", available_options=available_targets, constraints={}, history_segment=history_segment)
        request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{assassin_agent.player_id}", payload=action_request)
        response = await assassin_agent.receive_message(request_message)
        
        final_target_id = response.payload.action_data.target_player
        final_reasoning = response.payload.action_data.reasoning
        
        game_logger.info(f"The Minion has made their final decision.")
        game_logger.info(f"Final Target: Player {final_target_id}. Reasoning: {final_reasoning}")

        assassination_successful = (final_target_id == merlin_agent.player_id)
        assassination_result_message = BaseMessage(
            msg_type=MessageType.GAME_UPDATE, sender_id="GM", recipient_id="ALL",
            payload={
                "update_type": "ASSASSINATION_RESULT", "assassin_id": assassin_agent.player_id,
                "target_id": final_target_id, "merlin_id": merlin_agent.player_id,
                "assassination_successful": assassination_successful
            }
        )
        self.game_history.append(assassination_result_message)

        if assassination_successful:
            game_logger.info("\nThe Minion successfully assassinated Merlin! Evil wins!")
        else:
            game_logger.info(f"\nThe Minion failed to assassinate Merlin (who was Player {merlin_agent.player_id}). Good wins!")

if __name__ == "__main__":
    gm = GameMaster()
    try:
        asyncio.run(gm.run_game())
    finally:
        game_logger.info("\n--- Post-Game ---")
        
        # --- Cost Report ---
        game_logger.info("\n--- Post-Game Cost Report ---")
        total_game_cost = 0.0
        for agent in gm.agents:
            if isinstance(agent.llm_client, UnifiedLLMClient):
                cost = agent.llm_client.get_total_cost()
                total_game_cost += cost
                game_logger.info(f"Player {agent.player_id} ({agent.llm_client.model}): ${cost:.6f}")
        game_logger.info("-----------------------------")
        game_logger.info(f"Total Game Cost: ${total_game_cost:.6f}")

        # --- Context Saving ---
        game_logger.info("\nSaving player contexts...")
        all_contexts = {}
        for agent in gm.agents:
            if hasattr(agent.llm_client, 'history'):
                all_contexts[f"player_{agent.player_id}"] = {
                    "role": agent.role,
                    "model": agent.llm_client.model if hasattr(agent.llm_client, 'model') else 'mock',
                    "history": agent.llm_client.history
                }

        if all_contexts:
            context_filename = os.path.join(output_dir, f"game_context_{game_timestamp}.json")
            with open(context_filename, "w") as f:
                json.dump(all_contexts, f, indent=2)
            game_logger.info(f"Player contexts saved to {context_filename}")
            game_logger.info(f"You can now talk to the players using: python3 tools/talk_with_player.py <player_id> --context_file={context_filename}")
            game_logger.info(f"Available Player IDs: {list(all_contexts.keys())}")
        else:
            game_logger.info("No player contexts to save.")


