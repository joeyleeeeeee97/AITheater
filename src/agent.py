import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import os
import google.generativeai as genai
import time
from google.api_core import exceptions
import sys # Import sys module
import logging # Add this line

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
class DiscussionAction:
    action_type: str
    statement: Optional[str] = None
    target_player: Optional[int] = None
    reasoning: Optional[str] = None

@dataclass
class ActionResponsePayload:
    player_id: int
    action_type: str
    action_data: Union[DiscussionAction, TeamProposalAction, VoteAction, QuestAction, AssassinationAction, Any]
    llm_reasoning: Optional[str] = None
    response_time_ms: Optional[int] = None

# --- LLM and Prompt Management ---

class RealLLMClient:
    """A real LLM client."""
    def __init__(self, role: str, game_rules: str, role_context: str):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        self.logger = logging.getLogger(__name__) # Add this line
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('models/gemini-2.5-pro', system_instruction=f"{game_rules}\n{role_context}\nYou are a player in The Resistance: Avalon. Your role is {role}.")
        self.chat = self.model.start_chat(history=[])

    def generate(self, prompt: str) -> str:
        retries = 3
        for i in range(retries):
            try:
                response = self.chat.send_message(prompt)
                return response.text
            except (exceptions.ResourceExhausted, exceptions.InternalServerError) as e:
                self.logger.debug(f"API Error ({type(e).__name__}). Retrying in {2**(i+1)} seconds...")
                time.sleep(2**(i+1)) # Exponential backoff
            except Exception as e:
                self.logger.debug(f"An unexpected error occurred during LLM generation: {e}")
                raise
        raise Exception("LLM generation failed after multiple retries due to API issues.")

class MockLLMClient:
    """A mock LLM client for testing."""
    def __init__(self, role: str, game_rules: str, role_context: str):
        self.logger = logging.getLogger(__name__) # Add this line
        self.role = role
        self.game_rules = game_rules
        self.role_context = role_context
        self.history = [] # Simulate chat history

    def generate(self, prompt: str) -> str:
        self.history.append({"role": "user", "parts": [prompt]}) # Add user prompt to history
        self.logger.debug("--- Mock LLM Received Prompt ---")
        self.logger.debug(f"Role: {self.role}")
        self.logger.debug(f"{prompt}")
        self.logger.debug("--------------------------------")
        
        response_text = ""
        if "PARTICIPATE_DISCUSSION" in prompt:
            if self.role == "Merlin":
                response_text = "I have seen the evil, but for the greater good, I must remain silent. I will guide us to victory."
            elif self.role == "Assassin":
                response_text = "Hello everyone. I hope for an exciting game. I will observe everyone's words and actions carefully."
            else:
                response_text = "Hello everyone, I am a player. I am happy to play with you all."
        elif "PROPOSE_TEAM" in prompt:
            response_text = 'Team: [0, 1]\nReasoning: I believe these two players are trustworthy.'
        elif "VOTE_ON_TEAM" in prompt:
            response_text = 'Vote: approve\nReasoning: I trust this team.'
        elif "EXECUTE_QUEST" in prompt:
            if self.role in ["Merlin", "Percival", "Servant"]:
                response_text = 'Action: success\nReasoning: For Arthur!'
            else:
                response_text = 'Action: fail\nReasoning: For Mordred!'
        elif "ASSASSINATION_DECISION" in prompt:
            # Mock Assassin always targets player 0 (Merlin in our setup)
            response_text = 'Target: 0\nReasoning: I suspect player 0 is Merlin based on their subtle hints.'
        else:
            response_text = "This is a general response."
        
        self.history.append({"role": "model", "parts": [response_text]}) # Add model response to history
        return response_text

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

Your Identity: [Your Role, Your Allegiance (Loyal/Minion), and any secret knowledge you possess. e.g., "I am Merlin. I know Players C and F are Minions." or "I am a Minion of Mordred. Player F is my fellow Minion. I do not know who Merlin is."]

Game State: [Current Mission #, Current Leader, Players on the proposed team]

Game History:

Mission History: [Provide a list of past missions, the teams, the proposers, and the outcomes (Success/Fail, number of Fails played). e.g., "Mission 1 (2 players): Team [A, B], Proposed by A. Result: SUCCESS. Mission 2 (3 players): Team [A, C, D], Proposed by B. Result: FAIL (1 Fail card)."]

Vote History: [Provide a record of key team proposal votes, listing who voted Approve/Reject. e.g., "M2 Team Vote: Approve - A, C, D, F. Reject - B, E, G."]

Speech & Accusation Summary: [Provide a brief summary of significant statements or accusations. e.g., "After M2 failed, Player E accused Player D of failing. Player A has been quiet. Player C claims to be a 'confused Servant'."]

Current Accusations Against You: [List any specific accusations currently directed at you. e.g., "Player E is claiming I failed Mission 2 because I was on the team."]

## TASK ##

Based on the context above, formulate a single, powerful statement to be delivered to the other players. Your statement must be decisive and logical. Do not reveal your thought process, only the final statement.

Follow this internal reasoning framework to construct your statement:

Re-evaluate Your Objective: What is the single most important outcome for your team in this specific phase? (e.g., "Get this good team approved," "Get suspicion onto Player X," "Convince the table to reject this team so I can propose my own," "Protect my identity as Merlin," "Create chaos so the real Minions are overlooked.")

Analyze Historical Data for Weapons: Scrutinize the Game History. Find at least one specific piece of data (a vote, a past team composition, a prior statement) to use as the foundation for your argument.

Voting Patterns: Who always votes together? Who rejects teams they aren't on? Is there a player whose voting pattern seems illogical?

Mission Failures: Who are the common denominators on failed missions? Who was on the last failed mission? Who was on a successful mission and can be tentatively trusted?

Proposal Logic: Does the current proposed team make sense based on past results? Is the Leader deliberately including a suspicious player?

Address Accusations (If Applicable): If you are under suspicion, you must address it. Do not simply deny it. Attack the logic of the accusation or the motive of the accuser using historical data.

Example (as innocent): "Player E accuses me of failing Mission 2, but he conveniently forgets that he voted to APPROVE the team. If he was so sure a Minion was on it, why did he send it? The logical flaw in his action makes him more suspicious than me."

Example (as guilty): "Yes, I was on the failed mission, along with C and D. The fail could have come from any of us. However, look at the vote. Player B REJECTED that team. They clearly knew it would fail. My question is, how did Player B know? That is far more suspicious."

Construct Your Statement:

Begin with a clear and decisive stance (e.g., "This team must be rejected," "This is the safest team we can send," "I am voting APPROVE and here is why...").

Justify your stance using the specific historical data you identified in step 2. Name players and cite their specific actions (votes, proposals).

If necessary, weave in your defense from step 3.

Conclude with a call to action or a pointed question to put pressure on another player.

## OUTPUT FORMAT ##

Provide only the speech, written from a first-person perspective. Do not include labels like "Statement:" or explain your reasoning in the output.

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

    def get_quest_prompt(self, player_id: int, role: str, known_info: str, team: List[int]) -> str:
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
            # This logic is now handled by the LLM based on the detailed prompt below
            return self.cothought_prompt + f"""
ACTION: EXECUTE_QUEST
Your Player ID is {player_id}. Your role is {role}. You are a Minion of Mordred on a quest.
The current team is: {team}.
Your known information is: {known_info}

Your primary goal is to FAIL this quest. However, you must do so strategically to avoid being discovered. If multiple evil players fail the same quest, you will reveal too much information to the good players.

Therefore, you must coordinate with your fellow minions. Use the following priority system to decide who should fail the quest:
**Fail Priority: Minion > Morgana > Mordred**

1.  **Analyze the team:** Look at the players on the current team: {team}.
2.  **Identify evil players:** Based on your known info, who among them are your fellow minions?
3.  **Determine your priority:** Are you the highest-priority evil player ON THIS TEAM?
    *   If you are a **Minion**, and there are no other Minions on this team, you have the highest priority. You should probably play **fail**.
    *   If you are **Morgana**, and there are no Minions on this team, you have the highest priority. You should probably play **fail**.
    *   If you are **Mordred**, and there are no Minions or Morganas on this team, you have the highest priority. You should probably play **fail**.
    *   If there is a higher-priority evil player on the team, you should play **success** to conceal your identity.

Based on this strategic analysis, make your choice.

Format your response as:
Action: success|fail
Reasoning: [Provide a brief thought process for your decision based on the priority system. This reasoning is for your own reference and will not be shared.]
"""

    def get_assassination_prompt(self, player_id: int, role: str, available_targets: List[int]) -> str:
        return self.cothought_prompt + f"""
ACTION: ASSASSINATION_DECISION
Your Player ID is {player_id}. Your role is {role}.
The Loyal Servants of Arthur have successfully completed three missions.
This is your final chance to win the game for the Minions of Mordred. You have been designated to carry out the assassination. You must correctly identify and assassinate Merlin.

Analyze the entire game history. Look for players who seemed to have too much information, who guided the good players subtly, or whose voting patterns were suspicious. Merlin's goal is to appear like a normal Servant, so they will be hard to find. This is a difficult but critical decision.

Choose a player to assassinate from the available targets: {available_targets}.

Format your response as:
Target: player_id
Reasoning: Your detailed explanation for why you believe this player is Merlin.
"""

# --- RoleAgent Implementation ---

class RoleAgent:
    """An LLM-driven Avalon Agent that adheres to the protocol."""

    def __init__(self, player_id: int, llm_client_factory: Any):
        self.logger = logging.getLogger(__name__) # Add this line
        self.player_id = player_id
        self.role: Optional[str] = None
        self.game_id: Optional[str] = None
        self.known_info: Optional[str] = None
        self.llm_client_factory = llm_client_factory # Receives a factory function
        self.llm_client = None # Deferred initialization
        self.prompt_manager = PromptManager()
        self.known_history_index: int = 0 # Initialize known history index
        self.logger.debug(f"Agent {self.player_id} created.")

    def receive_message(self, message: BaseMessage) -> Optional[BaseMessage]:
        self.logger.debug(f"[Agent {self.player_id} ({self.role})] Received: {{'msg_type': '{message.msg_type.value}', 'sender_id': '{message.sender_id}', 'recipient_id': '{message.recipient_id}', 'msg_id': '{message.msg_id}', 'correlation_id': '{message.correlation_id}', 'payload': {json.dumps(message.payload, default=lambda o: o.__dict__, indent=2)}}})")
        if message.msg_type == MessageType.GAME_START:
            self._handle_game_start(message.payload)
        elif message.msg_type == MessageType.ACTION_REQUEST:
            response = self._handle_action_request(message)
            self.logger.debug(f"[Agent {self.player_id} ({self.role})] Sent: {{'msg_type': '{response.msg_type.value}', 'sender_id': '{response.sender_id}', 'recipient_id': '{response.recipient_id}', 'msg_id': '{response.msg_id}', 'correlation_id': '{response.correlation_id}', 'payload': {json.dumps(response.payload, default=lambda o: o.__dict__, indent=2)}}})")
            return response

    def _handle_game_start(self, payload: GameStartPayload):
        self.game_id = payload.game_id
        self.role = payload.role
        self.known_info = payload.initial_personal_info.get("known_info", "You have no special knowledge.")
        
        # Initialize LLM client here, passing role and game rules as system instructions
        game_rules = payload.game_rules # Get game rules from payload
        role_context = payload.role_context # Get role context from payload
        self.llm_client = self.llm_client_factory(self.role, game_rules, role_context)
        self.known_history_index = 0 # Reset for new game

        self.logger.debug(f"Agent {self.player_id} ({self.role}) initialized. Known info: {self.known_info}")

    def _handle_action_request(self, request_message: BaseMessage) -> BaseMessage:
        action_payload = request_message.payload
        response_payload = None

        if action_payload.action_type == "PARTICIPATE_DISCUSSION":
            prompt = self.prompt_manager.get_discussion_prompt(self.player_id, self.known_info, action_payload.history_segment)
            statement = self.llm_client.generate(prompt)
            action_data = DiscussionAction(action_type="statement", statement=statement)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "PROPOSE_TEAM":
            prompt = self.prompt_manager.get_propose_team_prompt(self.player_id, action_payload.constraints['team_size'], action_payload.history_segment)
            if action_payload.history_segment:
                prompt += f"\n\nPrevious Game History:\n{action_payload.history_segment}"
            response_str = self.llm_client.generate(prompt)
            
            # Parse plain text response
            lines = response_str.strip().split('\n')
            team_line = next((line for line in lines if line.startswith("Team:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)

            team_members = []
            reasoning = ""

            if team_line:
                team_members_str = team_line.replace("Team:", "").strip()
                try:
                    # Still need json.loads for list parsing, assuming LLM returns a valid list string
                    team_members = json.loads(team_members_str) # This might still fail if LLM doesn't return a valid list string
                except json.JSONDecodeError:
                    self.logger.debug(f"Warning: Could not parse team members from: {team_members_str}")
                    team_members = [] # Fallback to empty list
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
            response_str = self.llm_client.generate(prompt)
            
            # Parse plain text response (same as PROPOSE_TEAM)
            lines = response_str.strip().split('\n')
            team_line = next((line for line in lines if line.startswith("Team:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)

            team_members = []
            reasoning = ""

            if team_line:
                team_members_str = team_line.replace("Team:", "").strip()
                try:
                    team_members = json.loads(team_members_str)
                except json.JSONDecodeError:
                    self.logger.debug(f"Warning: Could not parse team members from: {team_members_str}")
                    team_members = action_payload.constraints.get('current_proposed_team', []) # Fallback to original team
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()

            action_data = TeamProposalAction(team_members=team_members, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "VOTE_ON_TEAM":
            prompt = self.prompt_manager.get_vote_prompt(self.player_id, action_payload.constraints['team'], action_payload.constraints['team_proposal_reasoning'])
            if action_payload.history_segment:
                prompt += f"\n\nPrevious Game History:\n{action_payload.history_segment}"
            response_str = self.llm_client.generate(prompt)
            
            # Parse plain text response
            lines = response_str.strip().split('\n')
            vote_line = next((line for line in lines if line.startswith("Vote:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)

            vote = "reject" # Default to reject for safety
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
                action_payload.constraints.get('team', [])
            )
            if action_payload.history_segment:
                prompt += f"\n\nPrevious Game History:\n{action_payload.history_segment}"
            response_str = self.llm_client.generate(prompt)
            
            # Parse plain text response
            lines = response_str.strip().split('\n')
            action_line = next((line for line in lines if line.startswith("Action:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)

            # Default to success for safety, especially for good roles.
            action = "success"
            reasoning = ""

            if action_line:
                action = action_line.replace("Action:", "").strip()
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()

            # Good players must succeed
            if self.role not in {"Mordred", "Morgana", "Minion", "Oberon"}:
                action = "success"

            action_data = QuestAction(action=action, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        elif action_payload.action_type == "ASSASSINATION_DECISION":
            prompt = self.prompt_manager.get_assassination_prompt(
                self.player_id,
                self.role,
                action_payload.available_options
            )
            if action_payload.history_segment:
                prompt += f"\n\nPrevious Game History:\n{action_payload.history_segment}"
            response_str = self.llm_client.generate(prompt)
            
            # Parse plain text response
            lines = response_str.strip().split('\n')
            target_line = next((line for line in lines if line.startswith("Target:")), None)
            reasoning_line = next((line for line in lines if line.startswith("Reasoning:")), None)

            target_player = -1 # Default to invalid target
            reasoning = ""

            if target_line:
                try:
                    target_player = int(target_line.replace("Target:", "").strip())
                except ValueError:
                    self.logger.debug(f"Warning: Could not parse target player from: {target_line}")
            if reasoning_line:
                reasoning = reasoning_line.replace("Reasoning:", "").strip()

            action_data = AssassinationAction(target_player=target_player, reasoning=reasoning)
            response_payload = ActionResponsePayload(player_id=self.player_id, action_type=action_payload.action_type, action_data=action_data)

        return BaseMessage(
            msg_type=MessageType.ACTION_RESPONSE,
            sender_id=f"PLAYER_{self.player_id}",
            recipient_id="GM",
            correlation_id=request_message.msg_id,
            payload=response_payload
        )