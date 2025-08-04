import sys
import os
import logging
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Logging Setup ---
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
game_file_handler = logging.FileHandler('game_output.log', mode='w')
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
debug_file_handler = logging.FileHandler('game_master_debug.log', mode='w')
debug_file_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_file_handler)
# --- End Logging Setup ---

from typing import List
from src.agent import RoleAgent, MockLLMClient, RealLLMClient, BaseMessage, MessageType, GameStartPayload, ActionRequest
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
        self._initialize_agents()

    def _initialize_agents(self):
        use_real_llm = os.environ.get("GEMINI_API_KEY") is not None
        llm_client_factory = RealLLMClient if use_real_llm else MockLLMClient
        
        self.agents = [RoleAgent(i, llm_client_factory) for i in range(self.num_players)]

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

    async def _run_team_building_phase(self):
        team_approved_for_quest = False
        self.consecutive_rejections = 0

        while not team_approved_for_quest:
            game_logger.info(f"\n--- Team Building Attempt (Leader: Player {self.quest_leader_id}) ---", flush=True)
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
        game_logger.info("\n--- Game Over ---")
        if self.good_quests_succeeded >= 3:
            # Good wins, but Assassin might assassinate Merlin
            await self._run_assassination_phase()
        elif self.evil_quests_failed >= 3:
            game_logger.info("Evil wins by failing 3 quests!", flush=True)
        else:
            game_logger.info("Game ended without a clear winner (should not happen in a full game). ")

    async def _start_game(self):
        role_setups = {
            5: ["Merlin", "Percival", "Servant", "Mordred", "Morgana"],
            6: ["Merlin", "Percival", "Servant", "Servant", "Mordred", "Morgana"],
            7: ["Merlin", "Percival", "Servant", "Servant", "Mordred", "Morgana", "Minion"],
            8: ["Merlin", "Percival", "Servant", "Servant", "Servant", "Mordred", "Morgana", "Minion"],
            # Add more setups as needed
        }

        roles = role_setups.get(self.num_players)
        if not roles:
            raise ValueError(f"No role setup defined for {self.num_players} players.")
        
        random.shuffle(roles) # Randomize role assignment
        
        # Dynamically determine evil roles for this game setup
        all_evil_roles = {"Mordred", "Morgana", "Minion", "Oberon", "Assassin"}
        self.evil_roles_in_game = [role for role in roles if role in all_evil_roles]
        
        try:
            game_rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "doc", "game_rules.md")
            with open(game_rules_path, 'r', encoding='utf-8') as f:
                game_rules_intro = f.read()
        except FileNotFoundError:
            debug_logger.error(f"Game rules file not found at {game_rules_path}")
            game_rules_intro = "Game rules could not be loaded."

        tasks = []
        for i, agent in enumerate(self.agents):
            assigned_role = roles[i]
            agent.role = assigned_role # Manually set agent's role here for later access
            
            known_info = self._generate_known_info(i, assigned_role, roles)
            initial_info = {"known_info": known_info}

            # Load base role context
            role_context_content = ""
            try:
                role_md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "doc", "roles", f"{assigned_role.lower()}.md")
                with open(role_md_path, 'r', encoding='utf-8') as f:
                    role_context_content = f.read()
            except FileNotFoundError:
                debug_logger.error(f"Role context file not found: {role_md_path}")
                role_context_content = f"No specific context file found for role: {assigned_role}"

            # If the role is evil, append the general evil strategies
            if assigned_role in self.evil_roles_in_game:
                try:
                    evil_md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "doc", "evil.md")
                    with open(evil_md_path, 'r', encoding='utf-8') as f:
                        evil_strategies = f.read()
                    role_context_content += "\n\n---\n\n## General Strategies for Evil Roles\n\n" + evil_strategies
                except FileNotFoundError:
                    debug_logger.error(f"Evil strategies file not found at {evil_md_path}")

            game_start_payload = GameStartPayload(game_id=self.game_id, player_id=i, role=assigned_role, total_players=self.num_players, game_rules=game_rules_intro, role_context=role_context_content, initial_personal_info=initial_info)
            start_message = BaseMessage(msg_type=MessageType.GAME_START, sender_id="GM", recipient_id=f"PLAYER_{i}", payload=game_start_payload)
            debug_logger.debug(f"[GM] Sending: {{'msg_type': '{start_message.msg_type.value}', 'sender_id': '{start_message.sender_id}', 'recipient_id': '{start_message.recipient_id}', 'msg_id': '{start_message.msg_id}', 'correlation_id': '{start_message.correlation_id}', 'payload': {json.dumps(start_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            tasks.append(agent.receive_message(start_message))
        
        await asyncio.gather(*tasks)
        self.quest_leader_id = random.randint(0, self.num_players - 1) # Randomly select first leader

    async def _run_discussion_and_proposal_phase(self):
        debug_logger.debug("--- Starting Discussion and Proposal Phase ---")
        
        team_sizes = {5: [2, 3, 2, 3, 3], 6: [2, 3, 4, 3, 4], 7: [2, 3, 3, 4, 4], 8: [3, 4, 4, 5, 5], 9: [3, 4, 4, 5, 5], 10: [3, 4, 4, 5, 5]}
        current_team_size = team_sizes.get(self.num_players, [])[self.quest_num - 1] if self.quest_num > 0 else 2

        leader = self.agents[self.quest_leader_id]
        game_logger.info(f"Leader (Player {leader.player_id}) is proposing a team.")
        history_segment = self._get_formatted_history_segment(leader.known_history_index)
        action_request = ActionRequest(action_type="PROPOSE_TEAM", description=f"Please select {current_team_size} players for the team.", available_options=[], constraints={"team_size": current_team_size}, history_segment=history_segment)
        request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{leader.player_id}", payload=action_request)
        debug_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
        response = await leader.receive_message(request_message)
        self.proposed_team = response.payload.action_data.team_members
        self.team_proposal_reasoning = response.payload.action_data.reasoning
        team_proposal_message = BaseMessage(
            msg_type=MessageType.GAME_UPDATE,
            sender_id="GM",
            recipient_id="ALL",
            payload={
                "update_type": "TEAM_PROPOSAL",
                "leader_id": leader.player_id,
                "proposed_team": self.proposed_team,
                "reasoning": self.team_proposal_reasoning
            }
        )
        self.game_history.append(team_proposal_message)
        leader.known_history_index = len(self.game_history)
        game_logger.info(f"Leader {leader.player_id} ({leader.role}) proposes initial team: {self.proposed_team} with reasoning: {self.team_proposal_reasoning}")

        current_player_idx = (self.quest_leader_id + 1) % self.num_players
        for _ in range(self.num_players - 1):
            agent = self.agents[current_player_idx]
            game_logger.info(f"Player {agent.player_id} ({agent.role}) is speaking.")
            history_segment = self._get_formatted_history_segment(agent.known_history_index)
            action_request = ActionRequest(action_type="PARTICIPATE_DISCUSSION", description="Please make your statement regarding the proposed team.", available_options=[], constraints={}, history_segment=history_segment)
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            debug_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            response = await agent.receive_message(request_message)
            self.game_history.append(response)
            agent.known_history_index = len(self.game_history)
            debug_logger.debug(f"[GM] Received from Player {agent.player_id}: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")
            game_logger.info(f"Player {agent.player_id} ({agent.role}) says: {response.payload.action_data.statement}")
            current_player_idx = (current_player_idx + 1) % self.num_players

        game_logger.info(f"Leader (Player {leader.player_id}) is making a final statement and confirming the team.")
        history_segment = self._get_formatted_history_segment(leader.known_history_index)
        action_request = ActionRequest(action_type="CONFIRM_TEAM", description="You have heard the discussion. Please make your final statement and confirm the team for voting.", available_options=[], constraints={"team_size": current_team_size, "current_proposed_team": self.proposed_team}, history_segment=history_segment)
        request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{leader.player_id}", payload=action_request)
        debug_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
        response = await leader.receive_message(request_message)
        if hasattr(response.payload.action_data, 'team_members') and response.payload.action_data.team_members is not None:
            self.proposed_team = response.payload.action_data.team_members
            self.team_proposal_reasoning = response.payload.action_data.reasoning
            team_proposal_message = BaseMessage(
                msg_type=MessageType.GAME_UPDATE,
                sender_id="GM",
                recipient_id="ALL",
                payload={
                    "update_type": "TEAM_PROPOSAL",
                    "leader_id": leader.player_id,
                    "proposed_team": self.proposed_team,
                    "reasoning": self.team_proposal_reasoning
                }
            )
            self.game_history.append(team_proposal_message)
        leader.known_history_index = len(self.game_history)
        game_logger.info(f"Leader {leader.player_id} ({leader.role}) confirms team for voting: {self.proposed_team} with reasoning: {self.team_proposal_reasoning}")

    def _get_formatted_history_segment(self, start_index: int) -> str:
        formatted_segment = []
        for i in range(start_index, len(self.game_history)):
            message = self.game_history[i]
            if message.msg_type == MessageType.ACTION_RESPONSE:
                if message.payload.action_type == "PARTICIPATE_DISCUSSION" and hasattr(message.payload.action_data, 'statement'):
                    player_id = message.payload.player_id
                    statement = message.payload.action_data.statement
                    formatted_segment.append(f"Player {player_id} said: {statement}")
                elif message.payload.action_type == "VOTE_ON_TEAM" and hasattr(message.payload.action_data, 'vote'):
                    player_id = message.payload.player_id
                    vote = message.payload.action_data.vote
                    reasoning = message.payload.action_data.reasoning
                    formatted_segment.append(f"Player {player_id} voted {vote} with reasoning: {reasoning}")
                elif message.payload.action_type == "PROPOSE_TEAM" and hasattr(message.payload.action_data, 'team_members'):
                    player_id = message.payload.player_id
                    team = message.payload.action_data.team_members
                    reasoning = message.payload.action_data.reasoning
                    formatted_segment.append(f"Player {player_id} proposed team {team} with reasoning: {reasoning}")
                elif message.payload.action_type == "EXECUTE_QUEST" and hasattr(message.payload.action_data, 'action'):
                    player_id = message.payload.player_id
                    action = message.payload.action_data.action
                    reasoning = message.payload.action_data.reasoning
                    formatted_segment.append(f"Player {player_id} chose to {action} the quest with reasoning: {reasoning}")
            elif message.msg_type == MessageType.GAME_UPDATE:
                update_type = message.payload.get("update_type")
                if update_type == "TEAM_PROPOSAL":
                    leader_id = message.payload.get("leader_id")
                    proposed_team = message.payload.get("proposed_team")
                    reasoning = message.payload.get("reasoning", "No reasoning provided.")
                    formatted_segment.append(f"Team Proposal: Player {leader_id} proposed team {proposed_team} with reasoning: {reasoning}")
                elif update_type == "VOTE_RESULT":
                    votes_info = message.payload.get("votes", [])
                    for vote_entry in votes_info:
                        player_id = vote_entry.get("player_id")
                        vote = vote_entry.get("vote")
                        formatted_segment.append(f"Player {player_id} voted {vote}.")
                    
                    proposed_team = message.payload.get("proposed_team")
                    team_approved = message.payload.get("team_approved")
                    formatted_segment.append(f"Vote Result: Team {proposed_team} was {'approved' if team_approved else 'rejected'}.")
                elif update_type == "QUEST_RESULT":
                    quest_num = message.payload.get("quest_num")
                    quest_succeeded = message.payload.get("quest_succeeded")
                    fail_votes = message.payload.get("fail_votes")
                    formatted_segment.append(f"Quest {quest_num} Result: {'Succeeded' if quest_succeeded else 'Failed'} with {fail_votes} fail votes.")
                elif update_type == "ASSASSINATION_RESULT":
                    assassin_id = message.payload.get("assassin_id")
                    target_id = message.payload.get("target_id")
                    assassination_successful = message.payload.get("assassination_successful")
                    if assassination_successful:
                        formatted_segment.append(f"Assassination Result: Assassin {assassin_id} successfully assassinated Merlin (Player {target_id}).")
                    else:
                        formatted_segment.append(f"Assassination Result: Assassin {assassin_id} failed to assassinate Merlin (targeted Player {target_id}).")
        return "\n".join(formatted_segment)

    async def _run_voting_phase(self):
        debug_logger.debug("--- Starting Voting Phase ---")
        
        tasks = []
        vote_agents = []
        for agent in self.agents:
            if agent.player_id == self.quest_leader_id:
                continue

            history_segment = self._get_formatted_history_segment(agent.known_history_index)
            action_request = ActionRequest(action_type="VOTE_ON_TEAM", description="Please vote on the proposed team.", available_options=["approve", "reject"], constraints={"team": self.proposed_team, "team_proposal_reasoning": self.team_proposal_reasoning}, history_segment=history_segment)
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            debug_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            tasks.append(agent.receive_message(request_message))
            vote_agents.append(agent)

        responses = await asyncio.gather(*tasks)

        all_player_votes = []
        for agent, response in zip(vote_agents, responses):
            all_player_votes.append({'player_id': agent.player_id, 'vote': response.payload.action_data.vote})
            agent.known_history_index = len(self.game_history)
            debug_logger.debug(f"[GM] Received from Player {agent.player_id}: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")

        all_player_votes.append({'player_id': self.quest_leader_id, 'vote': 'approve'})
        game_logger.info(f"Leader (Player {self.quest_leader_id}) automatically votes approve.")

        game_logger.info("--- Vote Results ---")
        for pv in all_player_votes:
            game_logger.info(f"Player {pv['player_id']} voted: {pv['vote']}")
        
        approve_votes = sum(1 for pv in all_player_votes if pv['vote'] == "approve")
        self.team_approved = approve_votes > self.num_players / 2
        vote_result_message = BaseMessage(
            msg_type=MessageType.GAME_UPDATE,
            sender_id="GM",
            recipient_id="ALL",
            payload={
                "update_type": "VOTE_RESULT",
                "proposed_team": self.proposed_team,
                "votes": all_player_votes,
                "team_approved": self.team_approved
            }
        )
        self.game_history.append(vote_result_message)
        game_logger.info(f"Vote Result: {approve_votes} approved, {self.num_players - approve_votes} rejected. Team {"approved" if self.team_approved else "rejected"}.")

    async def _run_quest_execution_phase(self):
        if not self.team_approved:
            game_logger.info("Team was not approved. Skipping quest execution.")
            return

        debug_logger.debug("--- Starting Quest Execution Phase ---")
        tasks = []
        quest_agents = []
        evil_roles = {"Mordred", "Morgana", "Minion", "Oberon"}

        for agent_id in self.proposed_team:
            agent = self.agents[agent_id]
            
            is_evil = agent.role in evil_roles
            available_options = ["success", "fail"] if is_evil else ["success"]
            
            description = "You are on the quest. Choose to 'success' or 'fail' the mission."
            if not is_evil:
                description = "You are a Loyal Servant of Arthur on the quest. You must choose 'success'."

            fails_needed = 2 if self.quest_num == 4 and self.num_players >= 7 else 1
            
            history_segment = self._get_formatted_history_segment(agent.known_history_index)
            action_request = ActionRequest(
                action_type="EXECUTE_QUEST",
                description=description,
                available_options=available_options,
                constraints={"team": self.proposed_team, "fails_needed": fails_needed},
                history_segment=history_segment
            )
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            debug_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            
            tasks.append(agent.receive_message(request_message))
            quest_agents.append(agent)
        
        responses = await asyncio.gather(*tasks)
        
        quest_results = []
        for agent, response in zip(quest_agents, responses):
            quest_results.append(response.payload.action_data.action)
            agent.known_history_index = len(self.game_history)
            debug_logger.debug(f"[GM] Received from Player {agent.player_id}: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")

        random.shuffle(quest_results)
        fail_votes = quest_results.count("fail")
        
        fails_needed = 2 if self.quest_num == 4 and self.num_players >= 7 else 1
        quest_succeeded = fail_votes < fails_needed

        game_logger.info(f"\n--- Quest {self.quest_num} Results ---")
        game_logger.info(f"Quest cards have been revealed: {quest_results}")
        game_logger.info(f"There were {fail_votes} fail votes.")
        game_logger.info(f"Quest {'SUCCEEDED' if quest_succeeded else 'FAILED'}.")

        quest_result_message = BaseMessage(
            msg_type=MessageType.GAME_UPDATE,
            sender_id="GM",
            recipient_id="ALL",
            payload={
                "update_type": "QUEST_RESULT",
                "quest_num": self.quest_num,
                "team": self.proposed_team,
                "quest_succeeded": quest_succeeded,
                "fail_votes": fail_votes,
                "revealed_cards": quest_results
            }
        )
        self.game_history.append(quest_result_message)

        if quest_succeeded:
            self.good_quests_succeeded += 1
        else:
            self.evil_quests_failed += 1

        self.quest_leader_id = (self.quest_leader_id + 1) % self.num_players

    def _check_game_end_condition(self) -> bool:
        if self.good_quests_succeeded >= 3:
            game_logger.info("Good wins by succeeding 3 quests!")
            return True
        if self.evil_quests_failed >= 3:
            game_logger.info("Evil wins by failing 3 quests!", flush=True)
            return True
        return False

    async def _finalize_game(self):
        game_logger.info("\n--- Game Over ---")
        if self.good_quests_succeeded >= 3:
            await self._run_assassination_phase()
        elif self.evil_quests_failed >= 3:
            game_logger.info("Evil wins by failing 3 quests!", flush=True)
        else:
            game_logger.info("Game ended without a clear winner (should not happen in a full game). ")

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
        game_logger.info("Saving player contexts...")
        
        all_contexts = {}
        for agent in gm.agents:
            # Ensure we only try to get history from real LLM clients
            if hasattr(agent.llm_client, 'chat'):
                history = agent.llm_client.chat.history
                # Convert the history objects to a serializable format
                serializable_history = [
                    {'role': msg.role, 'parts': [part.text for part in msg.parts]}
                    for msg in history
                ]
                all_contexts[f"player_{agent.player_id}"] = {
                    "role": agent.role,
                    "history": serializable_history
                }

        if all_contexts:
            with open("game_context.json", "w") as f:
                json.dump(all_contexts, f, indent=2)
            game_logger.info("Player contexts saved to game_context.json")
            game_logger.info("You can now talk to the players using: python3 talk_with_player.py <player_id>")
            game_logger.info("Available Player IDs:", list(all_contexts.keys()))
        else:
            game_logger.info("No real LLM player contexts to save.")

