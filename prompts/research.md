# A Cognitive Architecture for State-of-the-Art Play in The Resistance: Avalon

## Part 1: Foundational Knowledge and Core Game Logic

This document provides a comprehensive framework for developing a state-of-the-art agent for the social deduction game The Resistance: Avalon. It is structured in two parts. Part 1 establishes the formal rules, game-theoretic underpinnings, and core deductive heuristics necessary for high-level play. Part 2 details the specific cognitive processes and strategic imperatives for each major character role, designed to guide an agent's decision-making process.

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
The game state is represented and manipulated through a specific set of physical or digital components. An agent must possess a clear ontology of these objects.

*   **Character Cards:** Secretly assigned to each player, determining their allegiance (Good/Evil) and any special abilities.
*   **Leader Token:** Designates the player currently responsible for proposing a Quest Team.
*   **Team Tokens:** Used by the Leader to physically or visually assign players to the proposed Team.
*   **Vote Tokens:** A set of 'Approve' and 'Reject' tokens used by all players to vote on a proposed Team.
*   **Quest Cards:** A set of 'Success' and 'Fail' cards used by players on an approved Team to determine the outcome of the Quest.
*   **Score Markers:** Blue (Good/Arthur) and Red (Evil/Mordred) markers used to track the outcome of each Quest on the tableau.
*   **Round Marker:** A token that indicates which of the five Quests is currently being contested.
*   **Score Tableau:** A board that tracks the progress of the five Quests, the players required for each, and the vote track for Team proposals.

**1.3 Setup Protocol and Role Distribution**
The initial game state is established through a strict setup protocol that defines the game's core information asymmetry.

1.  **Board and Token Distribution:** The appropriate Score Tableau for the number of players is placed in the play area. Each player receives one 'Approve' and one 'Reject' Vote Token. A random player is selected to be the first Leader and receives the Leader Token.
2.  **Role Assignment:** The appropriate number of Good and Evil Character cards are selected based on player count. These cards are shuffled and one is dealt face-down to each player. Players secretly view their own role.
3.  **The "Night Phase" (Reveal Stage):** This scripted phase establishes the initial semi-private knowledge states. A moderator or the first Leader recites the following script, with players performing actions as instructed:
    *   "Everyone close your eyes and extend your hand into a fist in front of you."
    *   "Minions of Mordred (excluding Oberon), open your eyes and look around to know all agents of Evil." (This allows Evil players to identify each other).
    *   "Minions of Mordred, close your eyes."
    *   "Minions of Mordred (excluding Mordred), extend your thumb so that Merlin will know of you."
    *   "Merlin, open your eyes to see the agents of Evil." (This provides Merlin with knowledge of most, but not all, Evil players).
    *   "Merlin, close your eyes."
    *   "All players, put your thumbs down and re-form your hand into a fist."
    *   (If Percival and Morgana are in the game): "Merlin and Morgana, extend your thumb."
    *   "Percival, open your eyes to see Merlin and Morgana." (Percival knows the two players who are Merlin and Morgana, but does not know which is which).
    *   "Percival, close your eyes."
    *   "All players, put your thumbs down."
    *   "Everyone open your eyes."

The specific combination of roles used in a game significantly impacts its balance. The following table synthesizes official rules and established meta-play to provide standard, balanced configurations for an agent to train on.

| Total Players | Good Players | Evil Players | Quest Team Sizes (1-5) | 4th Quest Fails | Recommended Special Roles (Good) | Recommended Special Roles (Evil) |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **5** | 3 | 2 | 2, 3, 2, 3, 3 | 1 | Merlin, Percival | Morgana, Assassin |
| **6** | 4 | 2 | 2, 3, 4, 3, 4 | 1 | Merlin, Percival | Morgana, Assassin |
| **7** | 4 | 3 | 2, 3, 3, 4*, 4 | 2 | Merlin, Percival | Morgana, Oberon, Assassin |
| **8** | 5 | 3 | 3, 4, 4, 5*, 5 | 2 | Merlin, Percival | Morgana, Assassin, Minion |
| **9** | 6 | 3 | 3, 4, 4, 5*, 5 | 2 | Merlin, Percival | Mordred, Morgana, Assassin |
| **10**| 6 | 4 | 3, 4, 4, 5*, 5 | 2 | Merlin, Percival | Mordred, Morgana, Oberon, Assassin |
*(*Indicates that this Quest requires two 'Fail' cards to be considered a failure. In all other cases, one 'Fail' card is sufficient.*)

**1.4 The Sequence of Play: A State-Machine Approach**
The game progresses through a repeating cycle of phases, which can be modeled as a state machine for computational analysis.

*   **State 1: Team Building Phase**
    *   **1a. Team Proposal:** The current Leader selects players for the Quest Team, matching the number required on the Score Tableau for the current round.
    *   **1b. Discussion:** An unstructured period of open communication. Players may make any claims, accusations, or logical arguments to influence the upcoming vote.
    *   **1c. Voting:** All players, including the Leader, secretly select and then simultaneously reveal an 'Approve' or 'Reject' vote. A simple majority approves the team. A tied vote is a rejection.
    *   **1d. Transition:**
        *   **On Approval:** The game transitions to the Quest Phase (State 2).
        *   **On Rejection:** The Leader Token passes clockwise to the next player. The vote track marker is advanced. The game remains in the Team Building Phase. If this is the fifth consecutive rejection for the current Quest, the Evil team wins immediately.

*   **State 2: Quest Phase**
    *   **2a. Card Distribution:** Each player on the approved Team receives one 'Success' and one 'Fail' Quest card.
    *   **2b. Card Selection:** Team members secretly choose one card to play.
        *   Loyal Servants of Arthur **must** play 'Success'.
        *   Minions of Mordred **may** play either 'Success' or 'Fail'.
    *   **2c. Card Reveal:** The Leader collects the played cards, shuffles them to conceal individual plays, and reveals them to all players.

*   **State 3: Resolution Phase**
    *   **3a. Determine Outcome:** The Quest succeeds only if all revealed cards are 'Success'. If one or more 'Fail' cards are revealed, the Quest fails (with the exception of the 4th Quest in games of 7+ players, which requires two 'Fail' cards).
    *   **3b. Update Tableau:** A blue (Success) or red (Failure) Score Marker is placed on the tableau for the current Quest. The Round Marker is advanced to the next Quest space.
    *   **3c. Transition:** Check for game-end conditions. If neither faction has won, the game returns to State 1 with the new Leader.

**1.5 Special Game Mechanics: The Assassin's Gambit**
A crucial endgame mechanic fundamentally shapes the strategy of the entire game. If the Good team achieves three successful Quests, the game does not immediately end. Instead, the Assassination phase is triggered.

*   The Evil players may openly discuss amongst themselves.
*   The player with the **Assassin** role then makes a single, final declaration, naming one Good player they believe to be Merlin.
*   If the Assassin's guess is correct, the Evil faction overturns the result and **wins the game**. If the guess is incorrect, the Good faction's victory is confirmed.

---

## Part 2: Role-Specific Cognitive Architectures

This part provides a detailed cognitive model for each major role. It is structured as a pre-action checklist of questions that an agent should process to guide its behavior, ensuring its actions are aligned with the role's unique strategic imperatives.

### Section 5: The Good Allegiance: Servants of Arthur

#### 5.1 Merlin: The Burden of Knowledge
Merlin possesses the most powerful information in the game but is also the most vulnerable. Play is a delicate balance between guiding the Good team and ensuring personal survival.

*   **Primary Objective:** Guide the Good team to successfully complete three Quests.
*   **Secondary (Critical) Objective:** Avoid being identified and assassinated by the Evil team.
*   **Pre-Action Thought Process:**
    *   **When Proposing a Team:**
        1.  Is this a critical, must-pass Quest (e.g., the third fail is on the line)? If yes, proposing a team of players I know to be Good is paramount, despite the risk of exposure.
        2.  Is this an early-game Quest? Proposing a perfect team immediately is a very strong signal that I am Merlin. It may be strategically optimal to include one known spy on a two-person Quest 1 team, knowing it will fail, to create confusion and establish a non-omniscient persona.
        3.  How can I justify this team composition using only public information? I must construct a plausible public rationale for my choice that does not rely on my secret knowledge.
    *   **When Voting on a Team:**
        1.  Does this team contain any players I know to be Evil? If yes, the default action is to vote 'Reject'.
        2.  What is the likely outcome of the vote without my participation? If the team is likely to be approved anyway, my 'Reject' vote might not change the outcome but will be a strong signal to the Assassin.
        3.  Is it more valuable to protect my identity or to stop this team? In the early game, it can be correct to vote 'Approve' on a team with one spy to avoid being the sole 'Reject' voter. In the late game, stopping a failing team is almost always the correct play, even at the risk of exposure.
    *   **When Communicating:**
        1.  How can I subtly endorse a correct idea from a Loyal Servant? Simple agreement ("That's an interesting point" or "I see the logic in that") can steer the conversation without originating the idea myself.
        2.  How can I cast doubt on a spy without direct accusation? I can ask probing questions ("Player X, why did you approve the last team when you weren't on it?") or propose a flawed logical theory that coincidentally implicates a spy.
        3.  Should I feign confusion? To avoid appearing all-knowing, it is useful to occasionally express uncertainty or even float a theory that implicates a known Good player, creating valuable cover.

#### 5.2 Percival: The Protector's Dilemma
Percival's role is to solve a two-person mystery and then use that knowledge to protect the true Merlin, often by acting as a lightning rod for suspicion.

*   **Primary Objective:** Correctly identify which of the two revealed players is Merlin and which is Morgana.
*   **Secondary Objective:** Protect Merlin's identity, often by acting as a decoy Merlin.
*   **Pre-Action Thought Process:**
    *   **When Observing Merlin/Morgana:**
        1.  How are my two targets voting? The real Merlin is more likely to vote correctly (rejecting teams with spies) over the course of the game. Morgana may make "mistakes" or vote with her Evil allies.
        2.  How are my two targets communicating? Merlin's guidance is often subtle and suggestive. Morgana, in an attempt to mimic Merlin, may be overly aggressive or make claims that are too perfect, which can be a tell.
        3.  What happens when one of them is on a Quest? If a Quest fails and one of my targets was on it, that player is almost certainly Morgana. This is the most definitive piece of evidence I can obtain.
    *   **When Communicating:**
        1.  Have I identified Merlin yet? Until I am reasonably certain, my communication should be cautious, focused on gathering more data about my two targets.
        2.  Once I believe I know who Merlin is, how do I protect them? I must become the center of attention. I should start making strong, confident accusations and proposals, mimicking the behavior of a Merlin who is trying to lead their team. This makes me a more likely target for the Assassin.
        3.  How do I signal to Merlin that I know who they are? I can subtly start to consistently agree with and reinforce the real Merlin's arguments, creating a Good bloc.
    *   **When Voting:**
        1.  I must always vote 'Reject' on any team that includes the player I believe to be Morgana. This is a non-negotiable heuristic. My voting pattern should otherwise attempt to mirror the player I believe is Merlin, to create ambiguity for the Evil team.

#### 5.3 Loyal Servant of Arthur: The Uninformed Detective
The Loyal Servant is the purest deductive role. Lacking any special knowledge, their strength comes from rigorous analysis of public information and proactive engagement.

*   **Primary Objective:** Use public information (votes, mission history, dialogue) to deduce the identities of the Minions of Mordred.
*   **Secondary Objective:** Actively participate to generate information and provide cover for Merlin.
*   **Pre-Action Thought Process:**
    *   **On Information Generation:**
        1.  The game is currently ambiguous. What action can I take to force players to reveal information? I should propose controversial theories and vocalize my thought process. A quiet Servant provides no data and is not trusted. My goal is to provoke reactions.
        2.  Should I reject this team? As a default, if I am not on a team, I should vote to reject it. This forces more votes and generates more data. I must have a strong, publicly-stated reason to approve a team I am not on.
    *   **On Analyzing Accusations:**
        1.  Player X has just accused me of being Evil. Merlin knows I am a Loyal Servant. Therefore, Player X cannot be Merlin. This is a powerful deduction. I should now treat Player X with extreme suspicion and publicly state that their baseless accusation is a likely sign of them being Evil.
    *   **On Team Inclusion:**
        1.  How can I get onto the next mission? It is critical that I participate in missions. My presence on a successful mission helps establish a "clean" bloc. My presence on a failed mission narrows the pool of suspects. I must use logic and persuasion to convince the Leader to include me. Passivity is a losing strategy.

### Section 6: The Evil Allegiance: Minions of Mordred

#### 6.1 Assassin: The Hunter
The Assassin plays a dual role: a standard saboteur during the game, and the final arbiter of victory if Good succeeds. Every action should be viewed through the lens of gathering intelligence on Merlin's identity.

*   **Primary Objective:** Correctly identify Merlin for the end-game assassination.
*   **Secondary Objective:** Function as a Minion to fail Quests.
*   **Pre-Action Thought Process:**
    *   **On Constant Observation:**
        1.  Who is playing too well? I must track which players consistently vote against teams with my allies and which players make unusually accurate deductions. This is the primary signal of Merlin's presence.
        2.  Who is never surprised? Merlin is never surprised by a Quest failing. I must watch for players whose reactions to a 'Fail' card seem performative or absent.
        3.  Who is trying to subtly lead? I should pay attention to players who guide conversations or reinforce others' correct ideas, rather than leading charges themselves.
    *   **On the Percival/Morgana Dynamic:**
        1.  If these roles are in play, my task is more complex. I must observe the two players Percival is focused on. The one who plays more subtly and accurately is likely Merlin. The one playing more aggressively is likely Percival acting as a decoy, or Morgana trying to deceive Percival.
    *   **On the Final Decision:**
        1.  Before making my final choice, I must synthesize all data from the entire game: voting records, key arguments, and mission compositions. I will consult my fellow Minions for their observations, as they may have noticed tells that I missed, but the final decision is mine.

#### 6.2 Morgana: The False Prophet
Morgana's sole purpose, beyond being a standard Minion, is to exploit Percival's limited knowledge and neutralize him as a threat.

*   **Primary Objective:** Convince Percival that you are Merlin.
*   **Secondary Objective:** Fail Quests.
*   **Pre-Action Thought Process:**
    *   **On Mimicking Merlin:**
        1.  What would the real Merlin do? I must project an aura of cautious wisdom. I should vote against teams that include my Evil allies, as this is what Percival expects Merlin to do. My arguments should be logical and appear helpful, even if they lead to a suboptimal outcome for Good.
        2.  How do I avoid detection? The real Merlin is on my team. If I am on a mission that fails, Percival will know I am Morgana. Therefore, I must be extremely careful about when I choose to play a 'Fail' card.
    *   **On Manipulating Percival:**
        1.  My primary target is Percival's trust. It may be worth playing a 'Success' card on a mission with him to solidify his belief in me.
        2.  Once he trusts me, I can influence his votes and proposals, effectively turning one of Good's most powerful assets into a liability for them.
        3.  The ultimate goal is to get onto a critical late-game Quest with Percival's endorsement, then play a 'Fail' card to devastate the Good team and reveal the success of my deception.

#### 6.3 Mordred: The Hidden Blade
Mordred's invisibility to Merlin is a profound strategic advantage that must be carefully managed.

*   **Primary Objective:** Leverage your hidden status to fail a critical Quest without being immediately identified by Merlin.
*   **Secondary Objective:** Use your unique position to help identify Merlin.
*   **Pre-Action Thought Process:**
    *   **On Maintaining Cover:**
        1.  My core strategy is to be the most trustworthy player at the table. I must play like a perfect Loyal Servant, making sound, logical arguments based only on public information. My goal is to be included on late-game teams by the Good players' own volition.
    *   **On Observing Merlin:**
        1.  Merlin's actions towards me are not biased by knowledge of my true allegiance. If a player consistently argues against me or rejects teams I am on, they may be Merlin making a lucky guess, or they may simply be a good logician. I can use this ambiguity to my advantage, as Merlin has no definitive proof against me.
    *   **On Choosing When to Sabotage:**
        1.  If I am the only Minion on a Quest team, playing a 'Fail' card will instantly reveal my identity to Merlin. This is a move of last resort.
        2.  It is far better to wait for a Quest where another known Minion is present, so the blame is shared, or to save my sabotage for the final, game-deciding Quest.

#### 6.4 Oberon: The Agent of Chaos
Oberon is an Evil player who is blind to his allies. This role thrives on unpredictability and disrupting the information flow for both teams.

*   **Primary Objective:** Fail Quests.
*   **Secondary Objective:** Attempt to identify fellow Minions through observation to avoid counter-productive plays.
*   **Pre-Action Thought Process:**
    *   **On Deducing Allies:**
        1.  I must analyze voting patterns with the same rigor as a Good player. Players who form a consistent voting bloc and seem to have hidden knowledge are likely my allies. I must listen for subtle clues in their speech to try and align with them indirectly.
    *   **On Sabotaging Missions:**
        1.  This is extremely high-risk. If I am on a team with another Minion and we both play 'Fail' on a Quest that only requires one, we have likely handed the game to the Good team by exposing ourselves.
        2.  Unless I am certain I am the only Evil player on the team, or it is a Quest requiring two fails, playing 'Success' is often the safer and more strategic move.
    *   **On Communication:**
        1.  My ignorance is a weapon. I can genuinely argue against my fellow Minions, making the Evil team appear fractured and disorganized. This creates immense confusion for the Good players and makes it harder for them to identify a coherent Evil strategy. My role is to maximize chaos.

#### 6.5 Minion of Mordred: The Saboteur
The standard Minion is the backbone of the Evil team. Their play is focused on effective sabotage, clever deception, and assisting the Assassin.

*   **Primary Objective:** Cause three Quests to fail.
*   **Secondary Objective:** Gather and share information with allies to help the Assassin identify Merlin.
*   **Pre-Action Thought Process:**
    *   **On Early Game Strategy:**
        1.  Should I fail the first Quest? This is a critical decision dependent on the group's meta. Failing fast applies immediate pressure and seeds distrust among the Good team. However, it also immediately places me on a small list of suspects. A "slow play," where I play 'Success' on Quest 1, can build trust but cedes an early victory to Good.
    *   **On Coordinated Sabotage:**
        1.  If I am on a team with another Minion, who fails? A double-fail is catastrophic. There must be a clear, if unspoken, understanding. Generally, the Minion who is under less suspicion ("cooler") or has been on fewer failed Quests should be the one to play the 'Fail' card. The other should play 'Success' to maintain cover.
    *   **On Deception and Accusation:**
        1.  My entire persona must be that of a Good player. Every argument I make must be framed from that perspective.
        2.  When a Quest I am on fails, I must have a pre-prepared and logical-sounding argument for why another team member is the true saboteur. I must maintain this narrative with unwavering confidence.