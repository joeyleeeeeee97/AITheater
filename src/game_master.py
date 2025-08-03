import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='game_master_debug.log',
    filemode='w'
)
game_master_logger = logging.getLogger(__name__)

from typing import List
from src.agent import RoleAgent, MockLLMClient, RealLLMClient, BaseMessage, MessageType, GameStartPayload, ActionRequest
import json
import random

class GameMaster:
    """Manages the overall Avalon game flow."""

    def __init__(self, num_players: int = 5):
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

    def run_game(self):
        print("--- Game Start ---")
        self._start_game()

        while self.quest_num < 5 and not self._check_game_end_condition():
            self.quest_num += 1
            print(f"\n--- Starting Quest {self.quest_num} ---")
            # Call the new team building phase
            self._run_team_building_phase()
            self._run_quest_execution_phase()

        self._finalize_game()

    def _run_team_building_phase(self):
        team_approved_for_quest = False
        self.consecutive_rejections = 0

        while not team_approved_for_quest:
            print(f"\n--- Team Building Attempt (Leader: Player {self.quest_leader_id}) ---", flush=True)
            # This will be the new combined discussion and proposal phase
            self._run_discussion_and_proposal_phase()
            self._run_voting_phase() # This sets self.team_approved

            if self.team_approved:
                team_approved_for_quest = True
                self.consecutive_rejections = 0
            else:
                self.consecutive_rejections += 1
                print(f"Team rejected. Consecutive rejections: {self.consecutive_rejections}. Passing leadership.")
                self.quest_leader_id = (self.quest_leader_id + 1) % self.num_players
                if self.consecutive_rejections >= 5:
                    print("Five consecutive team rejections. Team is automatically approved.")
                    self.team_approved = True
                    team_approved_for_quest = True
                    self.consecutive_rejections = 0
        return self.team_approved

        self._finalize_game()

    def _start_game(self):
        roles = ["Merlin", "Percival", "Servant", "Mordred", "Minion"]
        random.shuffle(roles) # Randomize role assignment
        evil_players = {"Mordred", "Minion"}

        game_rules_intro = """Connected
V: 57.0.2
Wiki/Rules
Avalon: The Resistance - Official rules
Game Objective
Avalon: The Resistance is a strategic board game where players are tasked with completing a series of missions while dealing with hidden traitors known as Minions of Mordred. The game is set in the legendary world of King Arthur and the Knights of the Round Table.

Objective for the  Loyal Servants of Arthur
The Loyal 
Servant must successfully complete three out of five missions. They must work together to propose teams for each mission and vote on team compositions, always trying to keep traitors off the teams to prevent missions from failing.

Objective for the  Minions of Mordred
The 
Minion aim to sow discord and mistrust among the 
Servant. Their goal is to cause three missions to fail by infiltrating teams and sabotaging missions. They must communicate covertly and strategize to mislead the loyalists and cast doubt on the true allegiances of other players.

Additional Objectives
The game intensifies with special roles, such as 
Merlin, who knows the identities of the Minions but must keep his identity secret to avoid assassination at the end of the game. The Minions of Mordred can win by correctly identifying and assassinating 
Merlin after three missions have succeeded.

Gameplay Rules
1. Team Proposal and Voting
The player with the Leader token proposes a team of players for the mission. The number of players required for the team depends on the current mission and the total number of players in the game.
All players, including the Leader, then vote on the proposed team. A simple majority is required for the proposal to be accepted. If the proposal is rejected, the Leader token passes to the next player and a new proposal begins. If four proposals are rejected in a row, the fifth Leader has the power to choose the quest team without a vote.
2. Mission Phase
Once a team has been approved, members of the team secretly choose a Success  or Fail  card to determine the outcome of the mission.
All players submit their chosen cards to the Leader, who shuffles them to conceal which player submitted which card.
The cards are then revealed. For a mission to succeed, all the cards must be Success  cards. If one or more Fail  cards are revealed, the mission fails. Certain missions may require two Fail cards to fail, depending on the number of players in the game.
3. Progression of Play
After the outcome of the mission has been determined, the Leader token moves to the next player in clockwise order.
A new round begins with a new team proposal, and the same process repeats for a total of five missions.
Players must use their powers of persuasion, deduction, and bluffing to influence team selection, the vote, and discussion to further their side's agenda.
Conclusion of Gameplay
The gameplay continues through five missions, with the game ending once either the Loyal Servants of Arthur successfully complete three missions or the Minions of Mordred cause three missions to fail. In the case that the Loyal Servants of Arthur succeed, the Minions of Mordred have one final opportunity to win by correctly identifying 
Merlin, if they do so the Minions win.

Through strategic discussion, careful observation, and clever tactics, each side must do their best to achieve their objectives without revealing their true allegiances, making each round of Avalon: The Resistance play out uniquely and full of suspense.

Mission Team Size
Number of PlayersMission 1Mission 2Mission 3Mission 4Mission 5
5 Players23233
6 Players23434
7 Players2334*4
8 Players3445*5
9 Players3445*5
10 Players3445*5
Note: On missions marked with an asterisk (*), two Fail  cards are required for the mission to fail.

Recommended Roles Setup
General tips
For an enriching gaming experience, we suggest a group size of 7 to 10 players where the intricacies and excitement of the game truly shine.

For newcomers, it's advisable to begin your Avalon journey with the basic roles. As you become more accustomed to the gameplay, you can incrementally introduce additional roles, enhancing complexity and engagement step by step.

After the first games, we recommend adding roles in the following order:

Merlin -> 
Percival -> 
Morgana -> 
Oberon -> 
Mordred -> 
Lady of the lake -> 
Tristan + 
Isolde

5 Players:
Loyal Servants of Arthur: 
Merlin, 
Percival, 
Servant
Minions of Mordred: 
Mordred, 
Morgana
6 Players:
Loyal Servants of Arthur: 
Merlin, 
Percival, 
Servant, 
Servant
Minions of Mordred: 
Mordred, 
Morgana
7 Players:
Loyal Servants of Arthur: 
Merlin, 
Percival, 
Servant, 
Servant
Minions of Mordred: 
Mordred, 
Morgana, 
Minion
Expansions: 
Lady of the lake
8 Players:
Loyal Servants of Arthur: 
Merlin, 
Percival, 
Servant, 
Servant, 
Servant
Minions of Mordred: 
Mordred, 
Morgana, 
Minion
Expansions: 
Lady of the lake
9 Players:
Loyal Servants of Arthur: 
Merlin, 
Percival, 
Tristan, 
Isolde, 
Servant, 
Servant
Minions of Mordred: 
Mordred, 
Morgana, 
Minion
10 Players:
Loyal Servants of Arthur: 
Merlin, 
Percival, 
Servant, 
Servant, 
Servant, 
Servant
Minions of Mordred: 
Mordred, 
Morgana, 
Minion, 
Oberon
Expansions: 
Lady of the lake
Note: In the original version, there is a distinct role of the Assassin. We suggest delegating this function to any of the evil roles, or alternatively, making the decision collectively among the evil players.

Excalibur:
We recommend adding 
Excalibur to games for any number of players, but only in the company of experienced players.

Game setup in offline:
The default setup includes characters such as 
Merlin, 
Percival, and 
Morgana. However, you have the flexibility to customize the game by selecting the roles that best fit your group.

Everyone close your eyes and extend your hand info a fist in front of you.
Minion open your eyes and look around so that you know all agents of Evil.
Minion close your eyes
All players have their eyes closed and hands in a fist in front of them
Minion extend your thumb into the air so 
Merlin will known of you
Merlin open your eyes to see the agents of evil
Minion put your thumb down and re-form your hand into a fist
Merlin close your eyes
Merlin 
Morgana extend your thumb into the air so 
Percival will known of you
Percival open your eyes and see 
Merlin 
Morgana.
Merlin 
Morgana put your thumb down and re-form your hand into a fist
Percival close your eyes
All players have their eyes closed and hands in a fist in front of them
Everyone open your eyes
Note: For the purposes of game setup, the term "
"""

        for i, agent in enumerate(self.agents):
            assigned_role = roles[i]
            known_info = self._generate_known_info(i, assigned_role, roles)
            initial_info = {"known_info": known_info}

            # Merlin's specific knowledge is now handled in _generate_known_info
            # but if you need to pass other specific info, you can add it here.
            # For example:
            # if assigned_role == "Merlin":
            #     initial_info["known_evil_players"] = [p for p, r in enumerate(roles) if r in evil_players]

            role_md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "doc", "roles", f"{assigned_role.lower()}.md")
            try:
                with open(role_md_path, 'r', encoding='utf-8') as f:
                    role_context_content = f.read()
            except FileNotFoundError:
                game_master_logger.error(f"Role context file not found: {role_md_path}")
                role_context_content = "" # Fallback to empty string if file not found
            game_start_payload = GameStartPayload(game_id=self.game_id, player_id=i, role=assigned_role, total_players=self.num_players, game_rules=game_rules_intro, role_context=role_context_content, initial_personal_info=initial_info)
            start_message = BaseMessage(msg_type=MessageType.GAME_START, sender_id="GM", recipient_id=f"PLAYER_{i}", payload=game_start_payload)
            game_master_logger.debug(f"[GM] Sending: {{'msg_type': '{start_message.msg_type.value}', 'sender_id': '{start_message.sender_id}', 'recipient_id': '{start_message.recipient_id}', 'msg_id': '{start_message.msg_id}', 'correlation_id': '{start_message.correlation_id}', 'payload': {json.dumps(start_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            agent.receive_message(start_message)
        self.quest_leader_id = random.randint(0, self.num_players - 1) # Randomly select first leader

    def _run_discussion_and_proposal_phase(self):
        game_master_logger.debug("--- Starting Discussion and Proposal Phase ---")
        
        # Determine team size for the current quest
        # This is a placeholder; you'll need to implement actual team size logic based on quest_num and num_players
        team_sizes = {5: [2, 3, 2, 3, 3], 6: [2, 3, 4, 3, 4], 7: [2, 3, 3, 4, 4], 8: [3, 4, 4, 5, 5], 9: [3, 4, 4, 5, 5], 10: [3, 4, 4, 5, 5]}
        current_team_size = team_sizes.get(self.num_players, [])[self.quest_num - 1] if self.quest_num > 0 else 2

        # Leader's first proposal
        leader = self.agents[self.quest_leader_id]
        print(f"Leader (Player {leader.player_id}) is proposing a team.")
        history_segment = self._get_formatted_history_segment(leader.known_history_index)
        action_request = ActionRequest(action_type="PROPOSE_TEAM", description=f"Please select {current_team_size} players for the team.", available_options=[], constraints={"team_size": current_team_size}, history_segment=history_segment)
        request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{leader.player_id}", payload=action_request)
        game_master_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
        response = leader.receive_message(request_message)
        self.proposed_team = response.payload.action_data.team_members
        self.team_proposal_reasoning = response.payload.action_data.reasoning # Store the reasoning
        team_proposal_message = BaseMessage(
            msg_type=MessageType.GAME_UPDATE,
            sender_id="GM",
            recipient_id="ALL",
            payload={
                "update_type": "TEAM_PROPOSAL",
                "leader_id": leader.player_id,
                "proposed_team": self.proposed_team,
                "reasoning": self.team_proposal_reasoning # Include reasoning in game update
            }
        )
        self.game_history.append(team_proposal_message)
        leader.known_history_index = len(self.game_history)
        print(f"Leader {leader.player_id} ({leader.role}) proposes initial team: {self.proposed_team} with reasoning: {self.team_proposal_reasoning}")

        # Other players discuss in clockwise order
        current_player_idx = (self.quest_leader_id + 1) % self.num_players
        for _ in range(self.num_players - 1):
            agent = self.agents[current_player_idx]
            print(f"Player {agent.player_id} ({agent.role}) is speaking.")
            history_segment = self._get_formatted_history_segment(agent.known_history_index)
            action_request = ActionRequest(action_type="PARTICIPATE_DISCUSSION", description="Please make your statement regarding the proposed team.", available_options=[], constraints={}, history_segment=history_segment)
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            game_master_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            response = agent.receive_message(request_message)
            self.game_history.append(response)
            agent.known_history_index = len(self.game_history)
            game_master_logger.debug(f"[GM] Received from Player {agent.player_id}: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")
            print(f"Player {agent.player_id} ({agent.role}) says: {response.payload.action_data.statement}")
            current_player_idx = (current_player_idx + 1) % self.num_players

        # Leader's second proposal/summary
        print(f"Leader (Player {leader.player_id}) is making a final statement and confirming the team.")
        history_segment = self._get_formatted_history_segment(leader.known_history_index)
        action_request = ActionRequest(action_type="CONFIRM_TEAM", description="You have heard the discussion. Please make your final statement and confirm the team for voting.", available_options=[], constraints={"team_size": current_team_size, "current_proposed_team": self.proposed_team}, history_segment=history_segment)
        request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{leader.player_id}", payload=action_request)
        game_master_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
        response = leader.receive_message(request_message)
        # The leader might change the team here, so update self.proposed_team and reasoning
        if hasattr(response.payload.action_data, 'team_members') and response.payload.action_data.team_members is not None:
            self.proposed_team = response.payload.action_data.team_members
            self.team_proposal_reasoning = response.payload.action_data.reasoning # Update reasoning
            team_proposal_message = BaseMessage(
                msg_type=MessageType.GAME_UPDATE,
                sender_id="GM",
                recipient_id="ALL",
                payload={
                    "update_type": "TEAM_PROPOSAL",
                    "leader_id": leader.player_id,
                    "proposed_team": self.proposed_team,
                    "reasoning": self.team_proposal_reasoning # Broadcast final reasoning
                }
            )
            self.game_history.append(team_proposal_message)
        leader.known_history_index = len(self.game_history)
        print(f"Leader {leader.player_id} ({leader.role}) confirms team for voting: {self.proposed_team} with reasoning: {self.team_proposal_reasoning}")

    def _run_discussion_phase(self):
        # This method is now integrated into _run_discussion_and_proposal_phase
        pass

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
                    # Display individual votes from the detailed payload
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
            # Add other message types as needed for comprehensive history
        return "\n".join(formatted_segment)

    def _run_team_selection_phase(self):
        # This method is now integrated into _run_discussion_and_proposal_phase
        pass

    def _run_voting_phase(self):
        game_master_logger.debug("--- Starting Voting Phase ---")
        all_player_votes = [] # Store {'player_id': id, 'vote': vote} dictionaries
        for agent in self.agents:
            # Leader automatically approves their own team proposal
            if agent.player_id == self.quest_leader_id:
                all_player_votes.append({'player_id': agent.player_id, 'vote': 'approve'})
                print(f"Leader (Player {agent.player_id}) automatically votes approve.")
                continue

            history_segment = self._get_formatted_history_segment(agent.known_history_index)
            action_request = ActionRequest(action_type="VOTE_ON_TEAM", description="Please vote on the proposed team.", available_options=["approve", "reject"], constraints={"team": self.proposed_team, "team_proposal_reasoning": self.team_proposal_reasoning}, history_segment=history_segment)
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            game_master_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            response = agent.receive_message(request_message)
            all_player_votes.append({'player_id': agent.player_id, 'vote': response.payload.action_data.vote})
            agent.known_history_index = len(self.game_history) # Update agent's known history index
            game_master_logger.debug(f"[GM] Received from Player {agent.player_id}: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")
            # Removed immediate print of individual votes

        print("--- Vote Results ---")
        for pv in all_player_votes:
            print(f"Player {pv['player_id']} voted: {pv['vote']}")
        
        approve_votes = sum(1 for pv in all_player_votes if pv['vote'] == "approve")
        self.team_approved = approve_votes > self.num_players / 2
        # Record vote result in game history
        vote_result_message = BaseMessage(
            msg_type=MessageType.GAME_UPDATE,
            sender_id="GM",
            recipient_id="ALL",
            payload={
                "update_type": "VOTE_RESULT",
                "proposed_team": self.proposed_team,
                "votes": all_player_votes, # Now contains player_id and vote
                "team_approved": self.team_approved
            }
        )
        self.game_history.append(vote_result_message)
        print(f"Vote Result: {approve_votes} approved, {self.num_players - approve_votes} rejected. Team {"approved" if self.team_approved else "rejected"}.")

    def _run_quest_execution_phase(self):
        if not self.team_approved:
            print("Team was not approved. Skipping quest execution.")
            return

        game_master_logger.debug("--- Starting Quest Execution Phase ---")
        quest_results = []
        evil_roles = {"Mordred", "Morgana", "Minion", "Oberon"}

        for agent_id in self.proposed_team:
            agent = self.agents[agent_id]
            
            # Determine available actions based on role
            is_evil = agent.role in evil_roles
            available_options = ["success", "fail"] if is_evil else ["success"]
            
            description = "You are on the quest. Choose to 'success' or 'fail' the mission."
            if not is_evil:
                description = "You are a Loyal Servant of Arthur on the quest. You must choose 'success'."

            history_segment = self._get_formatted_history_segment(agent.known_history_index)
            action_request = ActionRequest(
                action_type="EXECUTE_QUEST",
                description=description,
                available_options=available_options,
                constraints={"team": self.proposed_team}, # Pass team info for strategic decisions
                history_segment=history_segment
            )
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{agent.player_id}", payload=action_request)
            game_master_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            
            response = agent.receive_message(request_message)
            quest_results.append(response.payload.action_data.action)
            agent.known_history_index = len(self.game_history)
            game_master_logger.debug(f"[GM] Received from Player {agent.player_id}: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")
            # Do not print individual actions to keep them secret
        
        # Shuffle results to hide who played what
        random.shuffle(quest_results)
        fail_votes = quest_results.count("fail")
        
        # Determine if quest succeeded (some missions require 2 fails)
        fails_needed = 2 if self.quest_num == 4 and self.num_players >= 7 else 1
        quest_succeeded = fail_votes < fails_needed

        print(f"\n--- Quest {self.quest_num} Results ---")
        print(f"Quest cards have been revealed: {quest_results}")
        print(f"There were {fail_votes} fail votes.")
        print(f"Quest {'SUCCEEDED' if quest_succeeded else 'FAILED'}.")

        # Record detailed quest result in game history
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

        # Pass leadership for the next quest
        self.quest_leader_id = (self.quest_leader_id + 1) % self.num_players

    def _check_game_end_condition(self) -> bool:
        if self.good_quests_succeeded >= 3:
            print("Good wins by succeeding 3 quests!")
            return True
        if self.evil_quests_failed >= 3:
            print("Evil wins by failing 3 quests!", flush=True)
            return True
        return False

    def _finalize_game(self):
        print("\n--- Game Over ---")
        if self.good_quests_succeeded >= 3:
            # Good wins, but Assassin might assassinate Merlin
            self._run_assassination_phase()
        elif self.evil_quests_failed >= 3:
            print("Evil wins by failing 3 quests!", flush=True)
        else:
            print("Game ended without a clear winner (should not happen in a full game). ")

    def _run_assassination_phase(self):
        game_master_logger.debug("--- Assassination Phase ---")
        assassin_agent = None
        merlin_agent = None

        # In this game version, any evil player can be the assassin.
        # We will designate one to perform the act.
        # Priority: Morgana, Mordred, Minion (as Assassin role may not be in game)
        potential_assassins = []
        evil_roles_for_assassination = ["Morgana", "Mordred", "Minion", "Assassin"]
        for agent in self.agents:
            if agent.role in evil_roles_for_assassination:
                potential_assassins.append(agent)
        
        if potential_assassins:
            # For simplicity, we'll designate the first one found.
            # A more complex system could involve voting among evil players.
            assassin_agent = potential_assassins[0]
            game_master_logger.info(f"Player {assassin_agent.player_id} ({assassin_agent.role}) has been designated to carry out the assassination.")

        for agent in self.agents:
            if agent.role == "Merlin":
                merlin_agent = agent
        
        if not merlin_agent:
            print("Error: Merlin not found in the game. Cannot proceed with assassination.")
            return

        if assassin_agent:
            history_segment = self._get_formatted_history_segment(assassin_agent.known_history_index)
            # Exclude the assassin from the list of targets
            available_targets = [str(a.player_id) for a in self.agents if a.player_id != assassin_agent.player_id]
            action_request = ActionRequest(action_type="ASSASSINATION_DECISION", description="The good team has won. As a designated evil player, you have one last chance to win by assassinating Merlin. Choose a player to assassinate.", available_options=available_targets, constraints={}, history_segment=history_segment)
            request_message = BaseMessage(msg_type=MessageType.ACTION_REQUEST, sender_id="GM", recipient_id=f"PLAYER_{assassin_agent.player_id}", payload=action_request)
            game_master_logger.debug(f"[GM] Sending: {{'msg_type': '{request_message.msg_type.value}', 'sender_id': '{request_message.sender_id}', 'recipient_id': '{request_message.recipient_id}', 'msg_id': '{request_message.msg_id}', 'correlation_id': '{request_message.correlation_id}', 'payload': {json.dumps(request_message.payload, default=lambda o: o.__dict__, indent=2)}}})")
            response = assassin_agent.receive_message(request_message)
            assassin_agent.known_history_index = len(self.game_history) # Update agent's known history index
            target_id = response.payload.action_data.target_player
            game_master_logger.debug(f"[GM] Received from Player {assassin_agent.player_id}: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")
            print(f"Designated Assassin (Player {assassin_agent.player_id}, {assassin_agent.role}) attempts to assassinate Player {target_id}.")
            
            assassination_successful = (target_id == merlin_agent.player_id)
            # Record assassination result in game history
            assassination_result_message = BaseMessage(
                msg_type=MessageType.GAME_UPDATE,
                sender_id="GM",
                recipient_id="ALL",
                payload={
                    "update_type": "ASSASSINATION_RESULT",
                    "assassin_id": assassin_agent.player_id,
                    "target_id": target_id,
                    "merlin_id": merlin_agent.player_id,
                    "assassination_successful": assassination_successful
                }
            )
            self.game_history.append(assassination_result_message)

            if assassination_successful:
                print("Assassin successfully assassinated Merlin! Evil wins!")
            else:
                print(f"Assassin failed to assassinate Merlin (who was Player {merlin_agent.player_id}). Good wins!")
        else:
            # This case should ideally not be reached if there are evil players.
            print("No evil players available to perform the assassination. Good wins by default.")

if __name__ == "__main__":
    gm = GameMaster()
    gm.run_game()
