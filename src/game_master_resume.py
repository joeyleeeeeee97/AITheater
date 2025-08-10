import sys
import os
import logging
import asyncio
from datetime import datetime
import yaml
import json
import random
from collections import Counter
import re
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import RoleAgent, BaseMessage, MessageType, ActionRequest, GameStartPayload

# --- Configuration ---
GAME_LOG_FILE = "outputs/game_output_2025-08-09_13-29-47.log"

# --- Logging Setup ---
game_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
output_dir = "outputs"
os.makedirs(output_dir, exist_ok=True)
log_filename = os.path.join(output_dir, f"game_resume_output_{game_timestamp}.log")
debug_log_filename = os.path.join(output_dir, f"game_resume_debug_{game_timestamp}.log")
plain_formatter = logging.Formatter('%(message)s')
debug_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
game_logger = logging.getLogger("game_flow")
game_logger.setLevel(logging.INFO)
game_logger.propagate = False
game_file_handler = logging.FileHandler(log_filename, mode='w')
game_file_handler.setFormatter(plain_formatter)
game_logger.addHandler(game_file_handler)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(plain_formatter)
game_logger.addHandler(console_handler)
debug_logger = logging.getLogger("debug")
debug_logger.setLevel(logging.DEBUG)
debug_logger.propagate = False
debug_file_handler = logging.FileHandler(debug_log_filename, mode='w')
debug_file_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_file_handler)
# --- End Logging Setup ---

class GameMasterResume:
    """A modified GameMaster that resumes the end-game sequence in stages for efficiency."""

    def __init__(self):
        self.agents: List[RoleAgent] = []
        self.game_result_message: str = ""
        self.config = {}
        self.role_contexts = {}
        self.num_players = 0
        self.game_history_log = ""
        self.roles = {0: "Loyal Servant", 1: "Morgana", 2: "Assassin", 3: "Oberon", 4: "Percival", 5: "Merlin", 6: "Loyal Servant"}
        self.evil_roles_in_game = ["Morgana", "Assassin", "Oberon"]
        self.context_review_prompt = ""

    async def resume_and_finish_game(self):
        """The main entry point for the staged resume script."""
        game_logger.info(f"--- Resuming Game from Log File: {GAME_LOG_FILE} ---")
        
        if not self._prepare_resume_environment():
            return

        # Stage 1: Assassination
        evil_ids = [pid for pid, role in self.roles.items() if role in ["Assassin", "Morgana", "Mordred"]]
        await self._initialize_and_brief_agents(evil_ids)
        await self._run_resumed_assassination_phase()
        
        # Stage 2: MVP
        good_ids = [pid for pid, role in self.roles.items() if role not in ["Assassin", "Morgana", "Mordred"]]
        await self._initialize_and_brief_agents(good_ids)
        await self._run_mvp_phase()
        
        game_logger.info("\n--- Post-Resume Cost Report ---")
        total_resume_cost = 0.0
        for agent in self.agents:
            if hasattr(agent, 'llm_client') and hasattr(agent.llm_client, 'get_total_cost'):
                cost = agent.llm_client.get_total_cost()
                total_resume_cost += cost
                game_logger.info(f"Player {agent.player_id} ({agent.role}): ${cost:.6f}")
        game_logger.info(f"Total Resume Cost: ${total_resume_cost:.6f}")

    def _prepare_resume_environment(self) -> bool:
        """Loads config and game log, preparing for agent initialization."""
        try:
            with open("config_test.yaml", 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            game_logger.error("CRITICAL: config_test.yaml not found. Exiting.")
            return False
        
        self.role_contexts = self._load_role_contexts()
        self.context_review_prompt = self._load_prompt_file("prompts/action/context_review.md")
        player_configs = self.config.get("player_setup", [])
        self.num_players = len(player_configs)
        if not player_configs:
            game_logger.error("CRITICAL: player_setup not found in config.yaml")
            return False

        try:
            with open(GAME_LOG_FILE, 'r') as f:
                self.game_history_log = f.read()
        except FileNotFoundError:
            game_logger.error(f"❌ CRITICAL: Game log file not found at {GAME_LOG_FILE}")
            return False
        
        game_logger.info("Resume environment prepared.")
        return True

    async def _initialize_and_brief_agents(self, player_ids: List[int]):
        """Initializes and briefs a specific list of agents with the game history."""
        game_logger.info(f"--- Initializing and briefing players: {player_ids} ---")
        player_configs = self.config.get("player_setup", [])
        game_rules = self._load_prompt_file("prompts/rules.md")

        for player_id in player_ids:
            if any(a.player_id == player_id for a in self.agents):
                continue

            player_config = next((p for p in player_configs if p['player_id'] == player_id), None)
            if not player_config:
                game_logger.error(f"No config found for player {player_id}")
                continue
            
            agent = RoleAgent(player_id, model_name=player_config['model'])
            agent.role = self.roles[player_id]
            role_context = self.role_contexts.get(agent.role, "")
            known_info = "You are resuming a game. The full history will be provided."
            
            start_payload = GameStartPayload(
                game_id="resumed_game", player_id=player_id, role=agent.role, total_players=self.num_players,
                game_rules=game_rules, role_context=role_context,
                initial_personal_info={"known_info": known_info}
            )
            start_message = BaseMessage(msg_type=MessageType.GAME_START, sender_id="GM_RESUME", recipient_id=f"PLAYER_{player_id}", payload=start_payload)
            await agent.receive_message(start_message)
            self.agents.append(agent)
            
            # Now, send the context review request
            review_prompt = self.context_review_prompt.replace("[PLAYER_ID]", str(player_id))
            review_prompt = review_prompt.replace("[PLAYER_ROLE]", agent.role)
            review_prompt = review_prompt.replace("[GAME_HISTORY_LOG]", self.game_history_log)

            review_req = ActionRequest(
                action_type="CONTEXT_REVIEW",
                description=review_prompt,
                available_options=[],
                constraints={}
            )
            review_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM_RESUME", recipient_id=f"PLAYER_{player_id}", payload=review_req) 
            # We don't need the response, just to prime the agent's context
            await agent.receive_message(review_msg) 
        
        self.agents.sort(key=lambda x: x.player_id)
        game_logger.info(f"Players {player_ids} are briefed and ready.")


    def _load_prompt_file(self, file_path: str) -> str:
        try:
            full_path = os.path.join(os.path.dirname(__file__), '..', file_path)
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            game_logger.error(f"Prompt file not found: {full_path}")
            return f"Error: Could not load file at {full_path}"

    def _load_role_contexts(self) -> dict:
        contexts = {}
        roles_dir = "prompts/roles"
        role_file_map = {
            "Merlin": "merlin.md", "Percival": "percival.md", "Loyal Servant": "loyal_servant.md",
            "Morgana": "morgana.md", "Mordred": "mordred.md", "Oberon": "oberon.md", "Assassin": "assassin.md"
        }
        for role, filename in role_file_map.items():
            path = os.path.join(roles_dir, filename)
            contexts[role] = self._load_prompt_file(path)
        return contexts

    async def _run_resumed_assassination_phase(self):
        game_logger.info("\n--- Running Resumed Assassination Phase ---")
        
        assassin_agent = next((agent for agent in self.agents if agent.role == "Assassin"), None)
        merlin_agent_id = next((pid for pid, role in self.roles.items() if role == "Merlin"), None)
        
        if not assassin_agent or merlin_agent_id is None:
            self.game_result_message = "Required role (Merlin/Assassin) not found. Cannot proceed."
            game_logger.error(self.game_result_message)
            return

        evil_team_for_discussion = [
            agent for agent in self.agents 
            if agent.role in self.evil_roles_in_game and agent.role != "Oberon"
        ]

        game_logger.info(f"\n--- Assassin's Proposal ---")
        available_targets = [str(pid) for pid, role in self.roles.items() if role not in self.evil_roles_in_game]
        
        proposal_req = ActionRequest(
            action_type="ASSASSINATE_PROPOSAL", 
            description="Propose a target to assassinate. Provide reasoning based on the game history.",
            available_options=available_targets, 
            constraints={}, 
            history_segment=self.game_history_log
        )
        proposal_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM_RESUME", recipient_id=f"PLAYER_{assassin_agent.player_id}", payload=proposal_req)
        proposal_response = await assassin_agent.receive_message(proposal_msg)
        
        proposal_target = proposal_response.payload.action_data.target_player
        proposal_reasoning = proposal_response.payload.action_data.reasoning
        game_logger.info(f"Assassin proposes targeting Player {proposal_target}. Reasoning: {proposal_reasoning}")

        game_logger.info(f"\n--- Evil Team Discussion ---")
        discussion_history = f"The Assassin has proposed targeting Player {proposal_target}. Reasoning: {proposal_reasoning}"
        discussion_tasks = []
        for teammate in evil_team_for_discussion:
            if teammate.player_id == assassin_agent.player_id:
                continue
            
            discussion_req = ActionRequest(
                action_type="ASSASSINATE_DISCUSSION",
                description="Provide counsel on the assassin's proposal.",
                available_options=[],
                constraints={'proposal_target': proposal_target, 'proposal_reasoning': proposal_reasoning},
                history_segment=self.game_history_log + "\n" + discussion_history
            )
            discussion_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM_RESUME", recipient_id=f"PLAYER_{teammate.player_id}", payload=discussion_req)
            discussion_tasks.append(teammate.receive_message(discussion_msg))

        if discussion_tasks:
            discussion_responses = await asyncio.gather(*discussion_tasks)
            for resp in discussion_responses:
                statement = resp.payload.action_data.statement
                game_logger.info(f"Counsel from Player {resp.payload.player_id} ({self.agents[resp.payload.player_id].role}): {statement}")
                discussion_history += f"\nPlayer {resp.payload.player_id} said: {statement}"

        game_logger.info(f"\n--- The Final Assassination ---")
        final_history_segment = self.game_history_log + "\n" + discussion_history

        final_decision_req = ActionRequest(
            action_type="ASSASSINATE_DECISION", 
            description="Make your final decision, taking your team's counsel into account.", 
            available_options=available_targets, 
            constraints={}, 
            history_segment=final_history_segment
        )
        final_decision_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM_RESUME", recipient_id=f"PLAYER_{assassin_agent.player_id}", payload=final_decision_req)
        final_response = await assassin_agent.receive_message(final_decision_msg)
        
        final_target_id = final_response.payload.action_data.target_player
        final_reasoning = final_response.payload.action_data.reasoning
        
        game_logger.info(f"The Assassin has targeted Player {final_target_id}.")
        game_logger.info(f"Final Reasoning: {final_reasoning}")

        if final_target_id == merlin_agent_id:
            self.game_result_message = f"\n✅ SUCCESS: The Assassin correctly assassinated Merlin (Player {merlin_agent_id})!"
            game_logger.info(self.game_result_message)
        else:
            self.game_result_message = f"\n❌ FAILURE: The Assassin failed to assassinate Merlin (who was Player {merlin_agent_id}), targeting Player {final_target_id} instead."
            game_logger.info(self.game_result_message)

    async def _run_mvp_phase(self):
        """Runs the post-game MVP selection, voting, and speech phase."""
        game_logger.info("\n--- Running MVP Selection Phase ---")
        game_logger.info("The roles for this game were:")
        for agent in self.agents:
            game_logger.info(f"Player {agent.player_id}: {agent.role}")
        
        game_logger.info("\n--- MVP Nominations ---")
        
        nomination_tasks = []
        for agent in self.agents:
            description = "The game is over. Please nominate a player for MVP. Your nomination must be in the format 'I nominate Player X' followed by your reasoning."
            action_request = ActionRequest(
                action_type="NOMINATE_MVP", 
                description=description, 
                available_options=[str(p.player_id) for p in self.agents], 
                constraints={},
                history_segment=self.game_history_log
            )
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM_RESUME", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            nomination_tasks.append(agent.receive_message(request_message))
            
        nomination_responses = await asyncio.gather(*nomination_tasks)

        votes = []
        for resp in nomination_responses:
            statement = resp.payload.action_data.statement
            game_logger.info(f"Player {resp.payload.player_id} ({self.agents[resp.payload.player_id].role}) says: {statement}")
            match = re.search(r'Player (\d+)', statement)
            if match:
                voted_for_id = int(match.group(1))
                if 0 <= voted_for_id < self.num_players:
                    votes.append(voted_for_id)
                    debug_logger.debug(f"Player {resp.payload.player_id} voted for Player {voted_for_id}")

        if not votes:
            game_logger.info("\nNo valid MVP nominations were cast.")
            return

        vote_counts = Counter(votes)
        mvp_id, mvp_votes = vote_counts.most_common(1)[0]
        
        top_voted_players = [p_id for p_id, count in vote_counts.items() if count == mvp_votes]
        if len(top_voted_players) > 1:
            game_logger.info(f"\nThere is a tie for MVP between players {top_voted_players} with {mvp_votes} votes each.")
            mvp_id = random.choice(top_voted_players)
            game_logger.info(f"Player {mvp_id} has been randomly selected as the winner.")
        
        mvp_agent = next((a for a in self.agents if a.player_id == mvp_id), None)
        if not mvp_agent:
            game_logger.error(f"Could not find MVP agent with ID {mvp_id}")
            return

        game_logger.info(f"\n--- MVP Announcement ---")
        game_logger.info(f"Player {mvp_id} ({mvp_agent.role}) has been elected as the MVP with {mvp_votes} votes!")

        game_logger.info(f"\n--- MVP Speech ---")
        speech_prompt = f"You have been elected as the MVP of the game! The final result was: '{self.game_result_message}'. Please give your victory/defeat speech."
        action_request = ActionRequest(action_type="MVP_SPEECH", description=speech_prompt, available_options=[], constraints={})
        request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM_RESUME", recipient_id=f"PLAYER_{mvp_id}", payload=action_request)
        response = await mvp_agent.receive_message(request_message)
        
        game_logger.info(f"MVP Player {mvp_id} ({mvp_agent.role}) says: {response.payload.action_data.statement}")

if __name__ == "__main__":
    gm_resume = GameMasterResume()
    try:
        asyncio.run(gm_resume.resume_and_finish_game())
    except Exception as e:
        game_logger.error(f"An unexpected error occurred: {e}", exc_info=True)