import uuid
import json
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Union, Tuple
import litellm

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Protocol Definitions ---

class MessageType(Enum):
    GAME_START = "game_start"
    GAME_UPDATE = "game_update"
    ACTION_REQUEST = "action_request"
    GAME_END = "game_end"
    ACTION_RESPONSE = "action_response"
    READY_SIGNAL = "ready_signal"
    ERROR_REPORT = "error_report"
    HEARTBEAT = "heartbeat"
    SHUTDOWN = "shutdown"

@dataclass
class BaseMessage:
    msg_type: MessageType
    sender_id: str
    recipient_id: str
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: Optional[str] = None
    payload: Any = None

@dataclass
class GameStartPayload:
    game_id: str
    player_id: int
    role: str
    total_players: int
    game_rules: str
    role_context: str
    initial_personal_info: Dict[str, Any]

@dataclass
class ActionRequest:
    action_type: str
    description: str
    available_options: list
    constraints: dict
    timeout_seconds: int = 60
    history_segment: Optional[str] = None

@dataclass
class TeamProposalAction:
    team_members: List[int]
    reasoning: str

@dataclass
class VoteAction:
    vote: str
    reasoning: str

@dataclass
class QuestAction:
    action: str
    reasoning: str

@dataclass
class AssassinationAction:
    target_player: int
    reasoning: str

@dataclass
class AssassinationProposalAction:
    target_player: int
    reasoning: str

@dataclass
class AssassinationDiscussionAction:
    statement: str
    reasoning: str

@dataclass
class DiscussionAction:
    action_type: str
    statement: Optional[str] = None
    target_player: Optional[int] = None
    reasoning: Optional[str] = None

@dataclass
class MvpNominationAction:
    statement: str
    reasoning: str

@dataclass
class ActionResponsePayload:
    player_id: int
    action_type: str
    action_data: Union[DiscussionAction, TeamProposalAction, VoteAction, QuestAction, AssassinationAction, AssassinationProposalAction, AssassinationDiscussionAction, MvpNominationAction, Any]
    llm_reasoning: Optional[str] = None
    response_time_ms: Optional[int] = None

# --- Unified LLM Client with Cost Tracking ---

class UnifiedLLMClient:
    """
    A unified LLM client using LiteLLM to support multiple providers,
    with built-in cost tracking.
    """
    def __init__(self, model: str, system_prompt: str):
        self.model = model
        self.system_prompt = system_prompt
        self.total_cost = 0.0
        self.logger = logging.getLogger("debug")
        self.history = [] # To store conversation history for context

    async def generate(self, prompt: str) -> Tuple[str, float]:
        # Add user prompt to history
        self.history.append({"role": "user", "content": prompt})
        
        messages = [{"role": "system", "content": self.system_prompt}] + self.history
        
        response_text = "Error: No response generated."
        cost = 0.0
        
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=messages
            )
            
            response_text = response.choices[0].message.content
            self.history.append({"role": "assistant", "content": response_text}) # Add model response to history
            
                        # Use litellm's cost tracking utility - this is NOT an async function
            cost = litellm.completion_cost(completion_response=response)
            self.total_cost += cost
            
        except Exception as e:
            self.logger.error(f"LLM generation failed for model {self.model}: {e}")
            response_text = f"I encountered an error and could not respond. (Error: {e})"
            # Do not add failed responses to history

        return response_text, float(cost)

    def get_total_cost(self) -> float:
        return self.total_cost

# --- Mock LLM Client for Testing ---

class MockLLMClient:
    """A mock LLM client for testing."""
    def __init__(self, model: str, system_prompt: str):
        self.logger = logging.getLogger("debug")
        self.role = "MockRole"
        self.history = []

    async def generate(self, prompt: str) -> Tuple[str, float]:
        self.history.append({"role": "user", "parts": [prompt]})
        self.logger.debug(f"--- Mock LLM Received Prompt (Role: {self.role}) ---\n{prompt}\n--------------------------------")
        
        response_text = "This is a mock response."
        # Simplified mock logic
        
        self.history.append({"role": "model", "parts": [response_text]})
        await asyncio.sleep(0.1)
        return response_text, 0.0

    def get_total_cost(self) -> float:
        return 0.0

class PromptManager:
    """Generates prompts based on game state."""
    def __init__(self):
        self.cothought_prompt = "Please forget you are an AI. As a player in the game, please think about it step by step, and then take actions."
        self.discussion_suffix = "\nProduce dialogue that aligns with your goals for the discussion. Note that dialogue will be seen by all players in the game. **Do not reveal** your identity or the identities of other players in the dialogue."

    def get_discussion_prompt(self, player_id: int, known_info: str, history_segment: str) -> str:
        prompt = self.cothought_prompt + f"""

ACTION: PARTICIPATE_DISCUSSION

LLM Prompt for Avalon Gameplay
You are a player in the game Avalon: The Resistance. It is your turn to speak during the discussion phase. Your objective is to make a persuasive and strategic statement that advances your side's goals. Your response must be based on a rigorous analysis of the game's history.

## CONTEXT ##

Your Identity: [Your Role, Your Allegiance (Loyal/Minion), and any secret knowledge you possess. e.g., \"I am Merlin. I know Players C and F are Minions.\" or \"I am a Minion of Mordred. Player F is my fellow Minion. I do not know who Merlin is.\"]

Game State: [Current Mission #, Current Leader, Players on the proposed team]

Game History:

Mission History: [Provide a list of past missions, the teams, the proposers, and the outcomes (Success/Fail, number of Fails played). e.g., \"Mission 1 (2 players): Team [A, B], Proposed by A. Result: SUCCESS. Mission 2 (3 players): Team [A, C, D], Proposed by B. Result: FAIL (1 Fail card).\"]

Vote History: [Provide a record of key team proposal votes, listing who voted Approve/Reject. e.g., \"M2 Team Vote: Approve - A, C, D, F. Reject - B, E, G.\"]

Speech & Accusation Summary: [Provide a brief summary of significant statements or accusations. e.g., \"After M2 failed, Player E accused Player D of failing. Player A has been quiet. Player C claims to be a 'confused Servant'.\"]

Current Accusations Against You: [List any specific accusations currently directed at you. e.g., \"Player E is claiming I failed Mission 2 because I was on the team.\"]

## TASK ##

Based on the context above, formulate a single, powerful statement to be delivered to the other players. Your statement must be decisive and logical. Do not reveal your thought process, only the final statement.

Follow this internal reasoning framework to construct your statement:

Re-evaluate Your Objective: What is the single most important outcome for your team in this specific phase? (e.g., \"Get this good team approved,\" \"Get suspicion onto Player X,\" \"Convince the table to reject this team so I can propose my own,\" \"Protect my identity as Merlin,\" \"Create chaos so the real Minions are overlooked.\")

Analyze Historical Data for Weapons: Scrutinize the Game History. Find at least one specific piece of data (a vote, a past team composition, a prior statement) to use as the foundation for your argument.

Voting Patterns: Who always votes together? Who rejects teams they aren't on? Is there a player whose voting pattern seems illogical?

Mission Failures: Who are the common denominators on failed missions? Who was on the last failed mission? Who was on a successful mission and can be tentatively trusted?

Proposal Logic: Does the current proposed team make sense based on past results? Is the Leader deliberately including a suspicious player?

Address Accusations (If Applicable): If you are under suspicion, you must address it. Do not simply deny it. Attack the logic of the accusation or the motive of the accuser using historical data.

Example (as innocent): \"Player E accuses me of failing Mission 2, but he conveniently forgets that he voted to APPROVE the team. If he was so sure a Minion was on it, why did he send it? The logical flaw in his action makes him more suspicious than me.\"

Example (as guilty): \"Yes, I was on the failed mission, along with C and D. The fail could have come from any of us. However, look at the vote. Player B REJECTED that team. They clearly knew it would fail. My question is, how did Player B know? That is far more suspicious.\"

Construct Your Statement:

Begin with a clear and decisive stance (e.g., \"This team must be rejected,\" \"This is the safest team we can send,\" \"I am voting APPROVE and here is why...\").

Justify your stance using the specific historical data you identified in step 2. Name players and cite their specific actions (votes, proposals).

If necessary, weave in your defense from step 3.

Conclude with a call to action or a pointed question to put pressure on another player.

## OUTPUT FORMAT ##

Provide only the speech, written from a first-person perspective. Do not include labels like \"Statement:\" or explain your reasoning in the output.

Your Player ID is {player_id}.
{known_info}

Your statement:
""" + self.discussion_suffix
        if history_segment:
            prompt += f"\n\nPrevious Game History:\n{history_segment}"
        return prompt

    def get_propose_team_prompt(self, player_id: int, team_size: int, history_segment: Optional[str]) -> str:
        # Add a specific instruction if there is no history yet.
        if not history_segment:
            initial_proposal_guidance = "This is the very first proposal of the game. Since there is no history, you must create a convincing argument for your initial team selection. You could base it on a general strategy (e.g., 'I am including myself to show I trust my own leadership') or a call for others to prove their loyalty. You can even use lighthearted reasons like 'I liked Player X's introduction'."
        else:
            initial_proposal_guidance = "Analyze the game history, player statements, and past votes to justify your choices."

        return self.cothought_prompt + f"""

ACTION: PROPOSE_TEAM
Your Player ID is {player_id}. You are the leader. Propose a team of {team_size} players.

Your reasoning is CRITICAL. You must provide a detailed, persuasive explanation for your team selection. **For each player you propose, you must give a specific reason for choosing them.** Your goal is to convince other players to approve your team.
{initial_proposal_guidance}

**YOU MUST FOLLOW THIS FORMAT EXACTLY:**
Team: [player_id1, player_id2, ...]
Reasoning: [Your detailed and persuasive explanation here, with a justification for each player.]
"""

    def get_confirm_team_prompt(self, player_id: int, team_size: int, current_team: List[int], history_segment: str) -> str:
        return self.cothought_prompt + f"""
ACTION: CONFIRM_TEAM
Your Player ID is {player_id}. You are the leader. You have listened to the discussion from the other players.
Your currently proposed team is {current_team}.

Review the discussion in the history below. Based on what you've heard, you must now make your final decision.
- You can **keep** your original team if the discussion was positive or you are confident in your choices.
- You can **change** your team if the discussion has raised valid concerns.

You must provide a final, persuasive reasoning for your confirmed team. This is your last chance to win votes.

**Game History of the discussion:**
{history_segment}

**YOU MUST FOLLOW THIS FORMAT EXACTLY:**
Team: [player_id1, player_id2, ...]
Reasoning: [Your final, detailed, and persuasive explanation for the team you are sending to the vote.]
"""

    def get_vote_prompt(self, player_id: int, team: List[int], team_proposal_reasoning: str) -> str:
        return self.cothought_prompt + f"""

ACTION: VOTE_ON_TEAM
Your Player ID is {player_id}. Vote on team {team}.
Team Proposal Reasoning: {team_proposal_reasoning}
Format your response as:
Vote: approve|reject
Reasoning: Your explanation here.
"""

    def get_quest_prompt(self, player_id: int, role: str, known_info: str, team: List[int], fails_needed: int) -> str:
        evil_roles = {"Mordred", "Morgana", "Minion", "Oberon"}
        is_evil = role in evil_roles

        if not is_evil:
            return self.cothought_prompt + f"""
ACTION: EXECUTE_QUEST
Your Player ID is {player_id}. You are a Loyal Servant of Arthur. You are on a quest.
You MUST choose 'success' to support the loyal servants of Arthur.

Format your response as:
Action: success
Reasoning: As a loyal servant, I must ensure the quest succeeds for the good of the kingdom.
"""
        else: # Evil role logic
            return self.cothought_prompt + f"""
ACTION: EXECUTE_QUEST
Your Player ID is {player_id}. Your role is {role}. You are a Minion of Mordred on a quest.
The current team is: {team}.
This mission requires {fails_needed} Fail card(s) to fail.
Your known information is: {known_info}

Your goal is to FAIL this quest, but with surgical precision. You must coordinate based on role priority to ensure the mission fails with the EXACT number of fail cards needed, revealing as little as possible.

**Fail Priority Order: Minion > Morgana > Mordred**

Follow these steps to decide your action:
1.  **Analyze the team:** Look at the players on the current team: {team}.
2.  **Identify Higher-Priority Teammates:** Based on your known info, count how many of your evil teammates ON THIS TEAM have a higher priority than you.
    *   If you are Mordred, count Minions and Morganas.
    *   If you are Morgana, count Minions.
    *   If you are a Minion, this count is always 0.
3.  **Make Your Decision:**
    *   **If the number of higher-priority teammates is GREATER THAN OR EQUAL TO {fails_needed}**: Your fail card is not needed. The mission will already be failed by your superiors. Your duty is to hide. Play **success**.
    *   **If the number of higher-priority teammates is LESS THAN {fails_needed}**: Your fail card IS required. You are one of the designated saboteurs for this mission. Play **fail**.

This logic ensures that if 2 fails are needed, and a Minion and Morgana are on the team, they both correctly identify that they must play Fail. If only 1 fail is needed, the Morgana will correctly deduce that the Minion will handle it, and will play Success to hide.

Format your response as:
Action: success|fail
Reasoning: [Provide a brief thought process for your decision based on the priority system and fails needed. This reasoning is for your own reference and will not be shared.]
"""

    def get_assassination_proposal_prompt(self, player_id: int, role: str, available_targets: List[int]) -> str:
        return self.cothought_prompt + f"""
ACTION: ASSASSINATE_PROPOSAL
Your Player ID is {player_id}. Your role is {role}. You are the designated assassin.
The Loyal Servants have won. This is your team's final chance. You must correctly identify and assassinate Merlin.
Analyze the entire game history. Look for players who seemed to have too much information, who subtly guided discussions, or whose actions seemed illogical for a simple Servant.
Propose a target for assassination to your fellow Minions. Provide clear, evidence-based reasoning for your choice. Your teammates will see this and give their feedback.
Available targets: {available_targets}.
Format your response as:
reasoning: Your final, detailed explanation for your choice, taking into account your team's discussion.
"""

    def get_mvp_nomination_prompt(self, player_id: int, role: str, history_segment: str) -> str:
        return self.cothought_prompt + f"""
ACTION: NOMINATE_MVP
Your Player ID is {player_id}. Your role was {role}. The game is now over.
Review your memory of the entire game and reflect on the performance of all players.
Based on your analysis, please provide a statement nominating one player for MVP.
Explain your reasoning clearly, citing specific plays, votes, or deductions that impressed you.

Format your response as:
Statement: [Your nomination statement and detailed reasoning.]
"""

# --- RoleAgent Implementation ---

class RoleAgent:
    """An LLM-driven Avalon Agent that adheres to the protocol."""

    def get_assassination_discussion_prompt(self, player_id: int, role: str, proposal_target: int, proposal_reasoning: str, history_segment: str) -> str:
        return self.cothought_prompt + f"""
ACTION: ASSASSINATE_DISCUSSION
Your Player ID is {player_id}. Your role is {role}. You are a Minion of Mordred, participating in the final assassination discussion.
Your assassin has proposed targeting Player {proposal_target} for the following reason: \"{proposal_reasoning}\" 
Review the discussion history below, including the initial proposal and any comments from other teammates.
**Discussion History:**
{history_segment}
Based on all the information, provide your counsel. Do you agree with the target? Do you have a different suspect? Provide your own analysis to help the assassin make the best final decision.
Format your response as:
Statement: [Your analysis and recommendation]
Reasoning: [Your thought process]
"""


    def get_assassination_final_decision_prompt(self, player_id: int, role: str, available_targets: List[int], history_segment: str) -> str:
        return self.cothought_prompt + f"""
ACTION: ASSASSINATE_DECISION
Your Player ID is {player_id}. Your role is {role}. You are the assassin.
You have proposed a target and have received counsel from your fellow Minions.
**Review the full discussion below:**
{history_segment}
This is the final moment. Weigh your initial analysis against the advice of your teammates. Make the final, game-deciding choice.
Choose a player to assassinate from the available targets: {available_targets}.
Format your response as:
Target: player_id
Reasoning: Your final, detailed explanation for your choice, taking into account your team's discussion.
"""

# --- RoleAgent Implementation ---

class RoleAgent:
    """An LLM-driven Avalon Agent that adheres to the protocol."""

    def __init__(self, player_id: int, model_name: str = "gpt-4-turbo"):
        self.logger = logging.getLogger("debug")
        self.player_id = player_id
        self.model_name = model_name # Store the model name
        self.role: Optional[str] = None
        self.game_id: Optional[str] = None
        self.known_info: Optional[str] = None
        self.llm_client: Optional[Union[UnifiedLLMClient, MockLLMClient]] = None
        self.prompt_manager = PromptManager()
        self.known_history_index: int = 0
        self.logger.debug(f"Agent {self.player_id} created, will use model: {self.model_name}")

    async def receive_message(self, message: BaseMessage) -> Optional[BaseMessage]:
        self.logger.debug(f"[Agent {self.player_id} ({self.role})] Received: {{'msg_type': '{message.msg_type.value}', 'sender_id': '{message.sender_id}', 'recipient_id': '{message.recipient_id}', 'msg_id': '{message.msg_id}', 'correlation_id': '{message.correlation_id}', 'payload': {json.dumps(message.payload, default=lambda o: o.__dict__, indent=2)}}})")
        if message.msg_type == MessageType.GAME_START:
            self._handle_game_start(message.payload)
        elif message.msg_type == MessageType.ACTION_REQUEST:
            response = await self._handle_action_request(message)
            self.logger.debug(f"[Agent {self.player_id} ({self.role})] Sent: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")
            return response

    def _handle_game_start(self, payload: GameStartPayload):
        self.game_id = payload.game_id
        self.role = payload.role
        self.known_info = payload.initial_personal_info.get("known_info", "You have no special knowledge.")
        
        system_prompt = f"{payload.game_rules}\n{payload.role_context}\nYou are a player in The Resistance: Avalon. Your role is {self.role}. "
        # Instantiate the LLM client directly with the stored model name
        self.llm_client = UnifiedLLMClient(model=self.model_name, system_prompt=system_prompt)
        self.known_history_index = 0

        self.logger.debug(f"Agent {self.player_id} ({self.role}) initialized. Known info: {self.known_info}")

    async def _handle_action_request(self, request_message: BaseMessage) -> BaseMessage:
        action_payload = request_message.payload
        response_payload = None
        debug_logger = logging.getLogger("debug")

        async def get_llm_response(prompt: str) -> str:
            response_text, cost = await self.llm_client.generate(prompt)
            debug_logger.debug(f"Player {self.player_id} ({self.role}) LLM call cost: ${cost:.6f}")
            return response_text

        if action_payload.action_type == "PARTICIPATE_DISCUSSION":
            prompt = self.prompt_manager.get_discussion_prompt(self.player_id, self.known_info, action_payload.history_segment)
            statement = await get_llm_response(prompt)
            action_data = DiscussionAction(action_type="statement", statement=statement)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "PROPOSE_TEAM":
            prompt = self.prompt_manager.get_propose_team_prompt(self.player_id, action_payload.constraints['team_size'], action_payload.history_segment)
            response_str = await get_llm_response(prompt)
            
            lines = response_str.strip().split('\n')
            team_line = next((line for line in lines if line.startswith("Team:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)
            team_members = []
            reasoning = ""
            if team_line:
                try:
                    team_members_str = team_line.replace("Team:", "").strip()
                    team_members = json.loads(team_members_str)
                except json.JSONDecodeError:
                    debug_logger.warning(f"Could not parse team members from: {team_members_str}")
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()
            action_data = TeamProposalAction(team_members=team_members, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "CONFIRM_TEAM":
            prompt = self.prompt_manager.get_confirm_team_prompt(
                self.player_id,
                action_payload.constraints['team_size'],
                action_payload.constraints['current_proposed_team'],
                action_payload.history_segment
            )
            response_str = await get_llm_response(prompt)
            
            lines = response_str.strip().split('\n')
            team_line = next((line for line in lines if line.startswith("Team:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)
            team_members = []
            reasoning = ""
            if team_line:
                try:
                    team_members_str = team_line.replace("Team:", "").strip()
                    team_members = json.loads(team_members_str)
                except json.JSONDecodeError:
                    debug_logger.warning(f"Could not parse team members from: {team_members_str}")
                    team_members = action_payload.constraints.get('current_proposed_team', [])
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()
            action_data = TeamProposalAction(team_members=team_members, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "VOTE_ON_TEAM":
            prompt = self.prompt_manager.get_vote_prompt(self.player_id, action_payload.constraints['team'], action_payload.constraints['team_proposal_reasoning'])
            response_str = await get_llm_response(prompt)
            
            lines = response_str.strip().split('\n')
            vote_line = next((line for line in lines if line.startswith("Vote:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)
            vote = "reject"
            reasoning = ""
            if vote_line:
                vote = vote_line.replace("Vote:", "").strip()
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()
            action_data = VoteAction(vote=vote, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "EXECUTE_QUEST":
            prompt = self.prompt_manager.get_quest_prompt(
                self.player_id,
                self.role,
                self.known_info,
                action_payload.constraints.get('team', []),
                action_payload.constraints.get('fails_needed', 1)
            )
            response_str = await get_llm_response(prompt)
            
            lines = response_str.strip().split('\n')
            action_line = next((line for line in lines if line.startswith("Action:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)
            action = "success"
            reasoning = ""
            if action_line:
                action = action_line.replace("Action:", "").strip()
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()
            if self.role not in {"Mordred", "Morgana", "Minion", "Oberon"}:
                action = "success"
            action_data = QuestAction(action=action, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "ASSASSINATE_PROPOSAL":
            prompt = self.prompt_manager.get_assassination_proposal_prompt(
                self.player_id,
                self.role,
                action_payload.available_options
            )
            response_str = await get_llm_response(prompt)
            
            lines = response_str.strip().split('\n')
            target_line = next((line for line in lines if line.startswith("Target:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)
            target_player = -1
            reasoning = ""
            if target_line:
                try:
                    target_player = int(target_line.replace("Target:", "").strip())
                except ValueError:
                    debug_logger.warning(f"Could not parse target player from: {target_line}")
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()
            action_data = AssassinationProposalAction(target_player=target_player, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "ASSASSINATE_DISCUSSION":
            prompt = self.prompt_manager.get_assassination_discussion_prompt(
                self.player_id,
                self.role,
                action_payload.constraints.get('proposal_target'),
                action_payload.constraints.get('proposal_reasoning'),
                action_payload.history_segment
            )
            response_str = await get_llm_response(prompt)
            
            lines = response_str.strip().split('\n')
            statement_line = next((line for line in lines if line.startswith("Statement:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)
            statement = ""
            reasoning = ""
            if statement_line:
                statement = statement_line.replace("Statement:", "").strip()
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()
            action_data = AssassinationDiscussionAction(statement=statement, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "ASSASSINATE_DECISION":
            prompt = self.prompt_manager.get_assassination_final_decision_prompt(
                self.player_id,
                self.role,
                action_payload.available_options,
                action_payload.history_segment
            )
            response_str = await get_llm_response(prompt)
            
            lines = response_str.strip().split('\n')
            target_line = next((line for line in lines if line.startswith("Target:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)
            target_player = -1
            reasoning = ""
            if target_line:
                try:
                    target_player = int(target_line.replace("Target:", "").strip())
                except ValueError:
                    debug_logger.warning(f"Could not parse target player from: {target_line}")
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()
            action_data = AssassinationAction(target_player=target_player, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "NOMINATE_MVP":
            prompt = self.prompt_manager.get_mvp_nomination_prompt(
                self.player_id,
                self.role,
                action_payload.history_segment
            )
            response_str = await get_llm_response(prompt)
            
            lines = response_str.strip().split('\n')
            statement_line = next((line for line in lines if line.startswith("Statement:")), None)
            statement = ""
            if statement_line:
                statement = statement_line.replace("Statement:", "").strip()
            
            action_data = MvpNominationAction(statement=statement, reasoning=response_str) # Store full response in reasoning
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        return BaseMessage(
            msg_type=MessageType.ACTION_RESPONSE,
            sender_id=f"PLAYER_{self.player_id}",
            recipient_id="GM",
            correlation_id=request_message.msg_id,
            payload=response_payload
        )