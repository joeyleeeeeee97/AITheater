# The Resistance: Avalon - Formal Rules and Game Logic

*This document is based on the formal specification from the Cognitive Architecture research guide.*

---

### Section 1: The Rules of Engagement: A Formal Specification of Avalon

A mastery of Avalon necessitates a precise, unambiguous understanding of its rule set. This section codifies the game's mechanics, objectives, and procedural flow, providing a definitive baseline for a computational agent.

**1.1 Core Objective and Factional Win Conditions**
The game is a contest between two factions with opposing objectives and asymmetric information.

*   **The Good Faction (Loyal Servants of Arthur):** The primary objective for the Good team is to successfully complete three of the five missions (referred to as Quests). A secondary, critical condition is that the identity of the character Merlin must remain concealed from the Evil faction. If both conditions are met, the Good team wins.
*   **The Evil Faction (Minions of Mordred):** The Evil team has three distinct paths to victory:
    1.  **Mission Sabotage:** Cause three Quests to end in failure.
    2.  **Assassination:** After the Good team has successfully completed three Quests, the Evil player with the Assassin role correctly identifies and names the player who is Merlin.
    3.  **Political Stalemate:** Force five consecutive proposed Teams for a single Quest to be rejected by vote.

**1.2 Game Components and Terminology**
*   **Character Cards:** Secretly assigned to each player, determining their allegiance (Good/Evil) and any special abilities.
*   **Leader Token:** Designates the player currently responsible for proposing a Quest Team.
*   **Vote Tokens:** A set of 'Approve' and 'Reject' tokens used by all players to vote on a proposed Team.
*   **Quest Cards:** A set of 'Success' and 'Fail' cards used by players on an approved Team to determine the outcome of the Quest.
*   **Score Markers:** Blue (Good/Arthur) and Red (Evil/Mordred) markers used to track the outcome of each Quest on the tableau.
*   **Round Marker:** A token that indicates which of the five Quests is currently being contested.
*   **Score Tableau:** A board that tracks the progress of the five Quests, the players required for each, and the vote track for Team proposals.

**1.3 Setup Protocol and Role Distribution**
1.  **Board and Token Distribution:** The appropriate Score Tableau for the number of players is placed in the play area. Each player receives one 'Approve' and one 'Reject' Vote Token. A random player is selected to be the first Leader and receives the Leader Token.
2.  **Role Assignment:** The appropriate number of Good and Evil Character cards are selected based on player count. These cards are shuffled and one is dealt face-down to each player. Players secretly view their own role.
3.  **The "Night Phase" (Reveal Stage):** This scripted phase establishes the initial semi-private knowledge states.
    *   "Everyone close your eyes and extend your hand into a fist in front of you."
    *   "Minions of Mordred (excluding Oberon), open your eyes and look around to know all agents of Evil."
    *   "Minions of Mordred, close your eyes."
    *   "Minions of Mordred (excluding Mordred), extend your thumb so that Merlin will know of you."
    *   "Merlin, open your eyes to see the agents of Evil."
    *   "Merlin, close your eyes."
    *   (If Percival and Morgana are in the game): "Merlin and Morgana, extend your thumb."
    *   "Percival, open your eyes to see Merlin and Morgana." (Percival does not know which is which).
    *   "Percival, close your eyes."
    *   "Everyone open your eyes."

**1.4 Standard Game Configurations**

| Total Players | Good Players | Evil Players | Quest Team Sizes (1-5) | 4th Quest Fails | Recommended Special Roles (Good) | Recommended Special Roles (Evil) |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **5** | 3 | 2 | 2, 3, 2, 3, 3 | 1 | Merlin, Percival | Morgana, Assassin |
| **6** | 4 | 2 | 2, 3, 4, 3, 4 | 1 | Merlin, Percival | Morgana, Assassin |
| **7** | 4 | 3 | 2, 3, 3, 4*, 4 | 2 | Merlin, Percival | Morgana, Oberon, Assassin |
| **8** | 5 | 3 | 3, 4, 4, 5*, 5 | 2 | Merlin, Percival | Morgana, Assassin, Minion |
| **9** | 6 | 3 | 3, 4, 4, 5*, 5 | 2 | Merlin, Percival | Mordred, Morgana, Assassin |
| **10**| 6 | 4 | 3, 4, 4, 5*, 5 | 2 | Merlin, Percival | Mordred, Morgana, Oberon, Assassin |
*(*Indicates that this Quest requires two 'Fail' cards to be considered a failure. In all other cases, one 'Fail' card is sufficient.*)

**1.5 The Sequence of Play: A State-Machine Approach**

*   **State 1: Team Building Phase**
    *   **1a. Team Proposal:** The current Leader selects players for the Quest Team.
    *   **1b. Discussion:** An unstructured period of open communication.
    *   **1c. Voting:** All players vote 'Approve' or 'Reject'. A simple majority approves the team. A tie is a rejection.
    *   **1d. Transition:** On Approval, proceed to State 2. On Rejection, pass the Leader token clockwise. If this is the 5th consecutive rejection **for the current Quest**, Evil wins immediately. This five-vote limit resets to zero for each new Quest.

*   **State 2: Quest Phase**
    *   **2a. Card Selection:** Team members secretly choose 'Success' or 'Fail'. (Loyal Servants **must** choose 'Success').
    *   **2b. Card Reveal:** The Leader shuffles and reveals the cards.

*   **State 3: Resolution Phase**
    *   **3a. Determine Outcome:** The Quest succeeds only if all cards are 'Success'.
    *   **3b. Update Tableau:** Mark the quest as Success or Failure.
    *   **3c. Transition:** Check for game-end conditions. If none are met, return to State 1.

**1.6 Special Game Mechanics: The Assassin's Gambit**
If the Good team achieves three successful Quests, the game is not over.
*   The Evil players may openly discuss.
*   The **Assassin** names one player they believe is Merlin.
*   If correct, **Evil wins**. If incorrect, **Good wins**.
