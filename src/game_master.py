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

from typing import List, Dict, Any
from src.agent import RoleAgent, BaseMessage, MessageType, GameStartPayload, ActionRequest
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
        self.team_proposal_reasoning = ""
        self.quest_leader_id = 0
        self.current_team: List[int] = []
        self.team_approved = False
        
        try:
            with open("config.yaml", 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            game_logger.error("CRITICAL: config.yaml not found. Exiting.")
            sys.exit(1)

        self.game_rules = self._load_prompt_file("prompts/rules.md")
        self.role_contexts = self._load_role_contexts()
        self.execute_quest_evil_prompt = self._load_prompt_file("prompts/execute_quest_evil.md")
        self.execute_quest_oberon_prompt = self._load_prompt_file("prompts/execute_quest_oberon.md")
        self.propose_team_prompt = self._load_prompt_file("prompts/action/propose_team.md")
        self.propose_team_evil_prompt = self._load_prompt_file("prompts/action/propose_team_evil.md")
        self.confirm_team_prompt = self._load_prompt_file("prompts/action/confirm_team.md")
        
        self._initialize_agents()

    def _load_prompt_file(self, file_path: str) -> str:
        """Loads content from a given prompt file."""
        try:
            full_path = os.path.join(os.path.dirname(__file__), '..', file_path)
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            game_logger.error(f"Prompt file not found: {full_path}")
            return f"Error: Could not load file at {full_path}"

    def _load_role_contexts(self) -> dict:
        """Loads all role guides from the prompts/roles directory."""
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

    def _initialize_agents(self):
        """Initializes RoleAgent instances based on the configuration."""
        player_configs = self.config.get("player_setup", [])
        for i in range(self.num_players):
            player_config = next((p for p in player_configs if p['player_id'] == i), None)
            if not player_config or 'model' not in player_config:
                raise ValueError(f"Configuration for player {i} is missing or does not specify a model in config.yaml")
            model_name = player_config['model']
            self.agents.append(RoleAgent(i, model_name=model_name))

    def _generate_known_info(self, player_id: int, role: str, roles: List[str]) -> str:
        """Generates the known_info string for a player based on their role."""
        evil_roles = {"Mordred", "Morgana", "Assassin"}
        if role in evil_roles and role != "Oberon":
            evil_teammates = [i for i, r in enumerate(roles) if r in evil_roles and i != player_id and r != "Oberon"]
            return f"You are a Minion of Mordred. Your fellow evil teammates are players {evil_teammates}."
        if role == "Merlin":
            visible_evil_roles = {"Morgana", "Oberon", "Assassin"}
            visible_evil_players = [i for i, r in enumerate(roles) if r in visible_evil_roles]
            info_str = f"You see evil in the hearts of players {visible_evil_players}."
            if "Mordred" in roles:
                info_str += " Be warned, the traitor Mordred is hidden from your sight."
            return info_str
        if role == "Percival":
            merlin_id = roles.index("Merlin") if "Merlin" in roles else -1
            morgana_id = roles.index("Morgana") if "Morgana" in roles else -1
            if merlin_id != -1 and morgana_id != -1:
                seen_players = random.sample([merlin_id, morgana_id], 2)
                return f"You see players {seen_players}. One is Merlin, and one is Morgana, but you do not know which is which."
        return "You have no special knowledge."

    async def _start_game(self):
        """Assigns roles and sends the initial game start message to all agents."""
        roles_config = self.config.get('roles', {})
        roles = roles_config.get(self.num_players, {}).get('roles', [])
        self.evil_roles_in_game = roles_config.get(self.num_players, {}).get('evil_roles', [])
        if not roles:
            raise ValueError(f"No role configuration found for {self.num_players} players in config.yaml")
        random.shuffle(roles)
        self.quest_leader_id = random.randint(0, self.num_players - 1)
        game_logger.info("--- Assigning Roles ---")
        for i, agent in enumerate(self.agents):
            agent.role = roles[i]
            game_logger.info(f"Player {i} is assigned role: {agent.role}")
        for i, agent in enumerate(self.agents):
            known_info = self._generate_known_info(i, agent.role, roles)
            start_payload = GameStartPayload(
                game_id=self.game_id, player_id=i, role=agent.role, total_players=self.num_players,
                game_rules=self.game_rules, role_context=self.role_contexts.get(agent.role, ""),
                initial_personal_info={"known_info": known_info}
            )
            start_message = BaseMessage(msg_type=MessageType.GAME_START, sender_id="GM", recipient_id=f"PLAYER_{i}", payload=start_payload)
            await agent.receive_message(start_message)
            self.game_history.append(start_message)
            agent.known_history_index = len(self.game_history)

    def _get_formatted_history_segment(self, start_index: int) -> str:
        """Formats a segment of the game history into a readable string."""
        if start_index >= len(self.game_history):
            return "No new events."
        
        segment = []
        for i in range(start_index, len(self.game_history)):
            msg = self.game_history[i]
            
            if msg.msg_type == MessageType.ACTION_RESPONSE and msg.payload:
                payload = msg.payload
                action_data = payload.action_data
                if payload.action_type == "PARTICIPATE_DISCUSSION":
                    segment.append(f"Player {payload.player_id} said: {action_data.statement}")
                elif payload.action_type == "PROPOSE_TEAM" or payload.action_type == "CONFIRM_TEAM":
                    segment.append(f"Leader {payload.player_id} proposed team: {action_data.team_members}. Reasoning: {action_data.reasoning}")

            elif msg.msg_type == MessageType.GAME_UPDATE and msg.payload:
                payload = msg.payload
                update_type = payload.get("update_type")
                if update_type == "VOTE_RESULT":
                    result_text = "Approved" if payload['result'] else "Rejected"
                    vote_details = ", ".join([f"P{pid}({v[0].upper()})" for pid, v in payload['votes'].items()])
                    segment.append(f"[SYSTEM] Team Vote Result: {result_text} (Approve: {payload['approve_votes']}, Reject: {payload['reject_votes']}). Votes: {vote_details}.")
                elif update_type == "QUEST_RESULT":
                    segment.append(f"[SYSTEM] Quest {self.quest_num} Result: {payload['result']}. Team was {payload['team']}. Fail cards played: {payload['fail_cards']}.")

        return "\n".join(segment)

    async def _run_discussion_and_proposal_phase(self):
        """Handles the team proposal, discussion, and final proposal confirmation."""
        leader_agent = self.agents[self.quest_leader_id]
        team_size = self.config['roles'][self.num_players]['team_sizes'][self.quest_num - 1]
        available_players = [p.player_id for p in self.agents]

        # Determine which prompt to use based on the leader's role
        is_evil_leader = leader_agent.role in self.evil_roles_in_game and leader_agent.role != "Oberon"
        base_prompt = self.propose_team_evil_prompt if is_evil_leader else self.propose_team_prompt
        
        # Step 1: Initial Proposal
        game_logger.info(f"\nLeader (Player {leader_agent.player_id}) is proposing a team of {team_size}...")
        history_segment = self._get_formatted_history_segment(leader_agent.known_history_index)
        
        proposal_prompt = base_prompt.replace("[X]", str(team_size))
        proposal_prompt_with_options = f"{proposal_prompt}\n\nYou MUST choose from the following available player IDs: {available_players}"

        initial_proposal_req = ActionRequest(action_type="PROPOSE_TEAM", description=proposal_prompt_with_options, available_options=available_players, constraints={'team_size': team_size}, history_segment=history_segment)
        initial_proposal_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{leader_agent.player_id}", payload=initial_proposal_req)
        initial_response = await leader_agent.receive_message(initial_proposal_msg)
        
        initial_team = initial_response.payload.action_data.team_members
        initial_reasoning = initial_response.payload.action_data.reasoning
        game_logger.info(f"Leader {leader_agent.player_id} initially proposed team: {initial_team}. Reasoning: {initial_reasoning}")
        self.game_history.append(initial_response)
        leader_agent.known_history_index = len(self.game_history)

        # Step 2: Team Discussion
        game_logger.info("\n--- Team Discussion ---")
        # Create a discussion order starting from the leader and wrapping around.
        # Every player, including the leader, gets a turn to speak.
        discussion_order = self.agents[self.quest_leader_id:] + self.agents[:self.quest_leader_id]
        
        for agent in discussion_order:
            history_segment = self._get_formatted_history_segment(agent.known_history_index)
            discussion_req = ActionRequest(action_type="PARTICIPATE_DISCUSSION", description="Discuss the proposed team.", available_options=[], constraints={'team': initial_team}, history_segment=history_segment)
            discussion_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=discussion_req)
            response = await agent.receive_message(discussion_msg)
            
            game_logger.info(f"Player {response.payload.player_id} ({self.agents[response.payload.player_id].role}) says: {response.payload.action_data.statement}")
            self.game_history.append(response)
            agent.known_history_index = len(self.game_history)
            
        # Step 3: Final Proposal
        game_logger.info(f"\n--- Leader's Final Decision ---")
        final_history_segment = self._get_formatted_history_segment(leader_agent.known_history_index)
        
        # Use the prompt from the loaded file, replacing placeholders
        final_proposal_desc = self.confirm_team_prompt
        final_proposal_desc = final_proposal_desc.replace("[initial_team]", str(initial_team))
        final_proposal_desc = final_proposal_desc.replace("[available_players]", str(available_players))
        
        final_proposal_req = ActionRequest(action_type="CONFIRM_TEAM", description=final_proposal_desc, available_options=available_players, constraints={'team_size': team_size, 'current_proposed_team': initial_team}, history_segment=final_history_segment)
        final_proposal_msg = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{leader_agent.player_id}", payload=final_proposal_req)
        final_response = await leader_agent.receive_message(final_proposal_msg)

        self.current_team = final_response.payload.action_data.team_members
        self.team_proposal_reasoning = final_response.payload.action_data.reasoning
        game_logger.info(f"Leader {leader_agent.player_id} has finalized the team to: {self.current_team}. Final Reasoning: {self.team_proposal_reasoning}")
        self.game_history.append(final_response)
        leader_agent.known_history_index = len(self.game_history)

    async def _run_voting_phase(self):
        """Handles the team voting phase and records the outcome."""
        game_logger.info("\n--- Team Voting ---")
        vote_tasks = []
        for agent in self.agents:
            history_segment = self._get_formatted_history_segment(agent.known_history_index)
            action_request = ActionRequest(action_type="VOTE_ON_TEAM", description="Vote on the current team proposal.", available_options=['approve', 'reject'], constraints={'team': self.current_team, 'team_proposal_reasoning': self.team_proposal_reasoning}, history_segment=history_segment)
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            vote_tasks.append(agent.receive_message(request_message))
            
        vote_responses = await asyncio.gather(*vote_tasks)
        
        votes = {resp.payload.player_id: resp.payload.action_data.vote for resp in vote_responses}
        approve_votes = sum(1 for vote in votes.values() if vote == 'approve')
        reject_votes = self.num_players - approve_votes
        
        game_logger.info(f"Vote Results: Approve: {approve_votes}, Reject: {reject_votes}")
        for player_id, vote in votes.items():
            game_logger.info(f"  - Player {player_id} voted: {vote}")

        self.team_approved = approve_votes > reject_votes

        # Record the detailed vote results to game history
        vote_result_payload = {
            "update_type": "VOTE_RESULT",
            "team": self.current_team,
            "leader": self.quest_leader_id,
            "votes": votes,
            "approve_votes": approve_votes,
            "reject_votes": reject_votes,
            "result": self.team_approved
        }
        vote_result_message = BaseMessage(msg_type=MessageType.GAME_UPDATE, sender_id="GM", recipient_id="ALL", payload=vote_result_payload)
        self.game_history.append(vote_result_message)
        # Update history index for all agents since this is public info
        for agent in self.agents:
            agent.known_history_index = len(self.game_history)

    async def _run_quest_execution_phase(self):
        """Handles the quest execution by the approved team and records the outcome."""
        if not self.team_approved:
            return

        game_logger.info(f"\n--- Quest Execution (Team: {self.current_team}) ---")
        quest_outcomes = []
        quest_tasks = []

        evil_players_on_team = [p for p in self.current_team if self.agents[p].role in self.evil_roles_in_game]
        fails_needed = 2 if self.quest_num == 4 and self.num_players >= 7 else 1

        for player_id in self.current_team:
            agent = self.agents[player_id]
            if agent.role not in self.evil_roles_in_game:
                quest_outcomes.append('success')
                game_logger.info(f"Player {player_id} (Good) automatically plays SUCCESS.")
            else:
                history_segment = self._get_formatted_history_segment(agent.known_history_index)
                
                if agent.role == "Oberon":
                    description = self.execute_quest_oberon_prompt
                    constraints = {'team': self.current_team, 'fails_needed': fails_needed}
                else:
                    description = self.execute_quest_evil_prompt
                    constraints = {'team': self.current_team, 'evil_teammates_on_quest': evil_players_on_team, 'fails_needed': fails_needed}

                action_request = ActionRequest(
                    action_type="EXECUTE_QUEST", description=description,
                    available_options=['success', 'fail'], constraints=constraints,
                    history_segment=history_segment
                )
                request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
                quest_tasks.append(agent.receive_message(request_message))

        if quest_tasks:
            quest_responses = await asyncio.gather(*quest_tasks)
            for resp in quest_responses:
                quest_outcomes.append(resp.payload.action_data.action)
                debug_logger.debug(f"Evil player {resp.payload.player_id} chose to {resp.payload.action_data.action} the quest.")

        random.shuffle(quest_outcomes)
        fail_cards = quest_outcomes.count('fail')
        
        quest_failed = fail_cards >= fails_needed
        if quest_failed:
            self.evil_quests_failed += 1
            result_str = "FAILED"
        else:
            self.good_quests_succeeded += 1
            result_str = "SUCCEEDED"
            
        game_logger.info(f"Quest {result_str}. Fail cards played: {fail_cards}")

        # Record the quest result to game history
        quest_result_payload = {
            "update_type": "QUEST_RESULT",
            "quest_num": self.quest_num,
            "team": self.current_team,
            "result": result_str,
            "fail_cards": fail_cards,
            "fails_needed": fails_needed
        }
        quest_result_message = BaseMessage(msg_type=MessageType.GAME_UPDATE, sender_id="GM", recipient_id="ALL", payload=quest_result_payload)
        self.game_history.append(quest_result_message)
        # Update history index for all agents
        for agent in self.agents:
            agent.known_history_index = len(self.game_history)

    async def run_game(self):
        game_logger.info("--- Game Start ---")
        await self._start_game()
        while self.quest_num < 5 and not self._check_game_end_condition():
            self.quest_num += 1
            game_logger.info(f"\n--- Starting Quest {self.quest_num} ---")
            await self._run_team_building_phase()
            await self._run_quest_execution_phase()
            if self.team_approved:
                self.quest_leader_id = (self.quest_leader_id + 1) % self.num_players
        await self._finalize_game()
        await self._run_mvp_phase()

    def _check_game_end_condition(self) -> bool:
        """Checks if the game has reached a conclusion."""
        if self.good_quests_succeeded >= 3:
            game_logger.info("Game end condition met: 3 successful quests.")
            return True
        if self.evil_quests_failed >= 3:
            game_logger.info("Game end condition met: 3 failed quests.")
            return True
        return False

    async def _run_team_building_phase(self):
        team_approved_for_quest = False
        self.consecutive_rejections = 0
        while not team_approved_for_quest:
            game_logger.info(f"\n--- Team Building Attempt #{self.consecutive_rejections + 1} (Leader: Player {self.quest_leader_id}) ---")

            # On the 6th attempt (after 5 rejections), the team is automatically approved.
            if self.consecutive_rejections >= 5:
                game_logger.info("This is the sixth and final team proposal. It will be automatically approved.")
                await self._run_discussion_and_proposal_phase()
                self.team_approved = True
                team_approved_for_quest = True
            else:
                await self._run_discussion_and_proposal_phase()
                await self._run_voting_phase()
                if self.team_approved:
                    team_approved_for_quest = True
                    self.consecutive_rejections = 0
                else:
                    self.consecutive_rejections += 1
                    game_logger.info(f"Team rejected. Consecutive rejections: {self.consecutive_rejections}. Passing leadership.")
                    self.quest_leader_id = (self.quest_leader_id + 1) % self.num_players
        
        return self.team_approved

    async def _finalize_game(self):
        """Announces the primary game result before moving to the MVP phase."""
        game_logger.info("\n--- Game Over ---")
        if self.good_quests_succeeded >= 3:
            await self._run_assassination_phase()
        elif self.evil_quests_failed >= 3:
            game_logger.info("Three quests have failed. Evil wins the game!")
        else:
            game_logger.info("The game has concluded without a clear win condition being met.")

    async def _run_mvp_phase(self):
        """Runs the post-game MVP selection phase."""
        game_logger.info("\n--- MVP Selection Phase ---")
        game_logger.info("The roles for this game were:")
        for agent in self.agents:
            game_logger.info(f"Player {agent.player_id}: {agent.role}")
        game_logger.info("\n--- MVP Statements ---")
        for agent in self.agents:
            action_request = ActionRequest(action_type="NOMINATE_MVP", description="State who you think was the MVP and why.", available_options=[str(p.player_id) for p in self.agents], constraints={})
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            response = await agent.receive_message(request_message)
            game_logger.info(f"Player {agent.player_id} ({agent.role}) says: {response.payload.action_data.statement}")

    async def _run_assassination_phase(self):
        debug_logger.debug("--- Assassination Phase ---")
        assassin_agent = next((agent for agent in self.agents if agent.role == "Assassin"), None)
        merlin_agent = next((agent for agent in self.agents if agent.role == "Merlin"), None)
        if not merlin_agent or not assassin_agent:
            game_logger.info("Required role (Merlin/Assassin) not found. Good wins by default.")
            return
        game_logger.info(f"\n--- The Final Assassination ---")
        game_logger.info(f"The Assassin (Player {assassin_agent.player_id}) will now make the final decision.")
        history_segment = self._get_formatted_history_segment(assassin_agent.known_history_index)
        available_targets = [str(a.player_id) for a in self.agents if a.role not in self.evil_roles_in_game]
        action_request = ActionRequest(action_type="ASSASSINATE_DECISION", description="Make your final decision.", available_options=available_targets, constraints={}, history_segment=history_segment)
        request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{assassin_agent.player_id}", payload=action_request)
        response = await assassin_agent.receive_message(request_message)
        final_target_id = response.payload.action_data.target_player
        game_logger.info(f"The Assassin has targeted Player {final_target_id}.")
        if final_target_id == merlin_agent.player_id:
            game_logger.info("\nThe Assassin successfully assassinated Merlin! Evil wins!")
        else:
            game_logger.info(f"\nThe Assassin failed to assassinate Merlin (who was Player {merlin_agent.player_id}). Good wins!")

if __name__ == "__main__":
    gm = GameMaster()
    try:
        asyncio.run(gm.run_game())
    finally:
        game_logger.info("\n--- Post-Game Cost Report ---")
        total_game_cost = 0.0
        for agent in gm.agents:
            if hasattr(agent, 'llm_client') and agent.llm_client:
                cost = agent.llm_client.get_total_cost()
                total_game_cost += cost
                game_logger.info(f"Player {agent.player_id} ({agent.llm_client.model}): ${cost:.6f}")
        game_logger.info(f"Total Game Cost: ${total_game_cost:.6f}")
        game_logger.info("\nSaving player contexts...")
        all_contexts = {}
        for agent in gm.agents:
            if hasattr(agent, 'llm_client') and agent.llm_client and hasattr(agent.llm_client, 'history'):
                all_contexts[f"player_{agent.player_id}"] = {
                    "role": agent.role, "model": agent.llm_client.model, "history": agent.llm_client.history
                }
        if all_contexts:
            context_filename = os.path.join(output_dir, f"game_context_{game_timestamp}.json")
            with open(context_filename, "w") as f:
                json.dump(all_contexts, f, indent=2)
            game_logger.info(f"Player contexts saved to {context_filename}")
