import copy
import json
from collections import defaultdict

import discord
from discord.ext import commands

from config import *


AST = '**[*](https://bc.esolangs.gay/nothing_here.txt "Forecasted from public premoves; might not be accurate")**'
NOT_USERS = discord.AllowedMentions(users=False)

bot = commands.Bot(
    command_prefix="+",
    allowed_mentions=discord.AllowedMentions(everyone=False, replied_user=False),
    intents=discord.Intents(
        guilds=True,
        members=True,
        messages=True,
        message_content=True,
    ),
    max_messages=None,
    help_command=None,
)

with open("data.json") as f:
    data = json.load(f)

def save():
    with open("data.json", "w") as f:
        json.dump(data, f)

def get_zone():
    for zone in bot.get_guild(GUILD_ID).categories:
        if zone.name.lower() == "in-game zone":
            return zone

def game_state():
    return discord.utils.get(get_zone().channels, name="game-state")

def bulletin():
    return discord.utils.get(get_zone().channels, name="public-bulletin")

def players():
    zone = get_zone()
    return [ps[0] for channel in zone.channels if len(ps := [m for m in channel.members if m.get_role(PLAYER_ROLE_ID)]) == 1]

def is_player(member):
    return member.get_role(PLAYER_ROLE_ID)

def is_alive(member):
    return member.get_role(ALIVE_ROLE_ID)

def can_vote(member):
    return is_alive(member) or member.get_role(DEAD_VOTE_ROLE_ID)

async def spend_vote(member):
    if is_alive(member) or not can_vote(member):
        raise ValueError("only dead players with votes can spend them")
    await member.remove_roles(discord.Object(id=DEAD_VOTE_ROLE_ID))
    await member.add_roles(discord.Object(id=DEAD_NO_VOTE_ROLE_ID))

def describe_range(r):
    describe_range.l = len(players())
    match r:
        case {"from": n, "to": m} if n == m-1:
            return f"{n}"
        case {"from": n, "to": describe_range.l}:
            return f"at least {n}"
        case {"from": 0, "to": n}:
            return f"less than {n}"
        case {"from": n, "to": m}:
            return f"between {n} and {m-1}"

def describe_premove(premove):
    match premove:
        case {"type": "no_vote"}:
            return "abstain due to lacking a vote token"
        case {"type": "constant", "value": v}:
            return "vote" if v else "abstain"
        case {"type": "actual", **r}:
            return f"vote if the vote count is {describe_range(r)}"
        case {"type": "prospective", **r}:
            return f"vote if the prospective vote count is {describe_range(r)}"
        case {"type": "butler", "who": user_id}:
            return f"vote if <@{user_id}> does"

def describe_premove_past(premove, failed):
    nawt = "not "*failed
    match premove:
        case {"type": "no-vote"}:
            return "because you had no vote token"
        case {"type": "constant", "value": v}:
            return ""
        case {"type": "actual", **r}:
            return f"because the vote count was {nawt}{describe_range(r)}"
        case {"type": "prospective", **r}:
            return f"because the prospective vote count was {nawt}{describe_range(r)}"
        case {"type": "butler", "who": user_id}:
            return f"because <@{user_id}> did"

def nomination_players(nom_pos):
    ps = players()
    start = ([p.id for p in ps].index(data["nominations"][nom_pos]["nominee"]) + 1) % len(ps)
    return ps[start:] + ps[:start]

def nomination_players_before(nom_pos, player):
    ps = nomination_players(nom_pos)
    return ps[:ps.index(player)]

def is_current(nom_pos):
    return data["to_vote"] is not None and nom_pos == data["current_nomination"]

def has_voted(nom_pos, player):
    if is_current(nom_pos):
        return data["to_vote"] > nomination_players(nom_pos).index(player)
    elif nom_pos < data["current_nomination"]:
        return True
    else:
        return False

def is_to_vote(nom_pos, player):
    return is_current(nom_pos) and nomination_players(nom_pos)[data["to_vote"]] == player

def seen_premove(nom_pos, player, to=None):
    premoves = data["nominations"][nom_pos]["premoves"].get(str(player.id))

    if premoves and (result := premoves.get("result")) is not None:
        return {"type": "constant", "value": result}
    if not can_vote(player):
        return {"type": "no_vote"}

    if not premoves:
        return None
    if player == to or has_voted(nom_pos, player):
        return premoves["private"] or premoves["public"]
    else:
        return premoves["public"]

def see_future_from(nom_pos, we_are, assume_abstains, player):
    ps = nomination_players(nom_pos)
    before_us = set(ps[:ps.index(player)])
    return eval_votes(nom_pos, we_are, assume_abstains & before_us | {player})

def eval_votes(nom_pos, we_are=None, assume_abstains=frozenset()):
    voters = set()
    count = 0
    nom = data["nominations"][nom_pos]

    for i, player in enumerate(nomination_players(nom_pos)):
        if player in assume_abstains:
            continue

        match seen_premove(nom_pos, player, to=we_are):
            case None:
                continue
            case {"type": "no_vote"}:
                decision = False
            case {"type": "constant", "value": c}:
                decision = c
            case {"type": "actual", "from": n, "to": m}:
                decision = n <= count < m
            case {"type": "prospective", "from": n, "to": m}:
                prosp = see_future_from(nom_pos, we_are, assume_abstains, player)
                decision = n <= len(prosp) < m
            case {"type": "butler", "who": user_id}:
                user = bot.get_user(user_id)
                prosp = see_future_from(nom_pos, we_are, assume_abstains, player)
                decision = user in prosp

        if has_voted(nom_pos, player):
            nom["premoves"].setdefault(str(player.id), {})["result"] = decision

        if decision:
            count += 1
            voters.add(player)

    return voters

def votes_necessary(before):
    return max([
        (sum(bool(is_alive(p)) for p in players()) + 1) // 2,
        *[len(eval_votes(nom_pos)) for nom_pos in range(before)],
    ])

def get_nominers(nom):
    guild = bot.get_guild(GUILD_ID)
    return guild.get_member(nom["nominator"]), guild.get_member(nom["nominee"])

def vote_complaint(we, outside):
    if is_alive(we):
        return None, False
    if not can_vote(we):
        return "You have spent your vote token and cannot vote.", True
    maybe_nom = None
    maybe_premove = None
    for i, nom in enumerate(data["nominations"]):
        if i == outside:
            continue
        premoves = nom["premoves"].get(str(we.id), {"public": None, "private": None})
        premove = premoves["private"] or premoves["public"]
        if premove == {"type": "constant", "value": True}:
            _, nominee = get_nominers(nom)
            msg_link = bulletin().get_partial_message(nom["message"]).jump_url
            return f"You intend to use your vote token on {nominee.global_name or nominee.name} ({msg_link}), and you cannot vote multiple times.", True
        elif premove and premove != {"type": "constant", "value": False}:
            maybe_nom = nom
            maybe_premove = premove
    if maybe_nom:
        _, nominee = get_nominers(maybe_nom)
        msg_link = bulletin().get_partial_message(maybe_nom["message"]).jump_url
        return f"You intend to {describe_premove(maybe_premove)} on {nominee.global_name or nominee.name} ({msg_link}). Keep in mind that you can only vote once.", False
    return "Keep in mind that you can only vote once.", False

def render_nomination(pos, we_are=None):
    current = data["current_nomination"]
    to_vote = data["to_vote"]
    this_is_current = is_current(pos)
    nom = data["nominations"][pos]
    nominator, nominee = get_nominers(nom)
    votes = eval_votes(pos, we_are)
    
    sort = "Current nomination" if this_is_current else "Premoved nomination" if pos >= current else "Nomination"
    embed = discord.Embed(title=f"{sort} of {nominee.global_name or nominee.name}")
    embed.set_footer(text=f"Nominated by {nominator.global_name or nominator.name}")
    if this_is_current:
        embed.colour = discord.Colour(0x178bff)
        embed.description = f"{len(votes & set(nomination_players(pos)[:to_vote]))} voted ({len(votes)} expected{AST}, {votes_necessary(current)} needed)"
    elif pos >= current:
        embed.colour = discord.Colour(0xfffa66)
        embed.description = f"{len(votes)} expected to vote{AST} ({votes_necessary(pos)} needed{AST})"
    else:
        embed.colour = discord.Colour(0xc4e2ff)
        embed.description = f"{len(votes)} voted"

    votes_field = []
    for i, player in enumerate(nomination_players(pos)):
        our_premoves = nom["premoves"].get(str(player.id)) if player == we_are else None

        if has_voted(pos, player):
            voted = player in votes
            result = "**voted**" if voted else "abstained"
            if our_premoves:
                desc = describe_premove_past(our_premoves["private"] or our_premoves["public"], voted)
                votes_field.append(f"You {result} {desc}")
            else:
                votes_field.append(f"{player.mention} {result}")
        elif is_to_vote(pos, player):
            votes_field.append(f"{player.mention} is choosing an option...")
        elif action := seen_premove(pos, player, to=we_are):
            desc = describe_premove(action)
            if player in votes:
                desc = f"**{desc}**"
            if our_premoves:
                secretly = "(secretly) "*bool(action != seen_premove(pos, player))
                votes_field.append(f"You {secretly}will {desc}")
            else:
                votes_field.append(f"{player.mention} will {desc}")
    if votes_field:
        embed.add_field(name="Votes", value="\n".join(votes_field))

    if we_are and not is_alive(we_are) and not has_voted(pos, we_are):
        embed.add_field(name="You are dead", value=vote_complaint(we_are, pos)[0], inline=False)

    return embed

async def rerender_nomination(nom_pos):
    msg_id = data["nominations"][nom_pos]["message"]
    await bulletin().get_partial_message(msg_id).edit(embed=render_nomination(nom_pos))
    panels = voting_panels[msg_id]
    deads = []
    for idx, (interaction, panel) in enumerate(panels):
        try:
            await interaction.edit_original_response(embed=render_nomination(nom_pos, we_are=interaction.user), view=panel.format_self())
        except discord.HTTPException:
            deads.append(idx)
    for dead in deads[::-1]:
        panels.pop(dead)

class NominationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction):
        if not is_player(interaction.user):
            await interaction.response.send_message("Hey, you're not a player!", ephemeral=True)
            return False
        return True

    def find_nom_pos(self, interaction):
        return discord.utils.find(lambda nom: nom[1]["message"] == interaction.message.id, enumerate(data["nominations"]))[0]

    async def quick_action(self, interaction, vote):
        nom_pos = self.find_nom_pos(interaction)
        if has_voted(nom_pos, interaction.user):
            return await interaction.response.send_message("Your choice in this nomination is already locked in.", ephemeral=True)
        await interaction.response.defer()
        data["nominations"][nom_pos]["premoves"][str(interaction.user.id)] = {"public": {"type": "constant", "value": vote}, "private": None}
        save()
        if is_to_vote(nom_pos, interaction.user):
            await step_through()
        else:
            await rerender_nomination(nom_pos)

    @discord.ui.button(label="Open voting panel", style=discord.ButtonStyle.grey, custom_id="open_voting_panel")
    async def open_panel(self, interaction, button):
        nom_pos = self.find_nom_pos(interaction)
        panel = VotingPanel(nom_pos, interaction.user)
        await interaction.response.send_message(embed=render_nomination(nom_pos, we_are=interaction.user), view=panel, ephemeral=True)
        voting_panels[interaction.message.id].append((interaction, panel))

    @discord.ui.button(label="Quick vote", style=discord.ButtonStyle.red, custom_id="quick_vote")
    async def quick_vote(self, interaction, button):
        complaint, is_fatal = vote_complaint(interaction.user, self.find_nom_pos(interaction))
        if is_fatal:
            return await interaction.response.send_message(complaint, ephemeral=True)
        await self.quick_action(interaction, True)

    @discord.ui.button(label="Quick abstain", style=discord.ButtonStyle.blurple, custom_id="quick_abstain")
    async def quick_abstain(self, interaction, button):
        await self.quick_action(interaction, False)

class Subselector(discord.ui.Select):
    pass

class NumericSelect(Subselector):
    def __init__(self, labeller, callback, current, start, stop):
        super().__init__(options=[discord.SelectOption(label=labeller(x), value=str(x), default=x == current) for x in range(start, stop)])
        self.cb = callback

    async def callback(self, interaction):
        await self.cb(int(self.values[0]))
        save()
        await interaction.response.defer()

class PlayerSelect(Subselector):
    def __init__(self, callback, without, current):
        super().__init__(options=[discord.SelectOption(label=x.global_name or x.name, value=str(x.id), default=x.id == current) for x in players() if x != without])
        self.cb = callback

    async def callback(self, interaction):
        await self.cb(int(self.values[0]))
        save()
        await interaction.response.defer()

voting_panels = defaultdict(list)

class VotingPanel(discord.ui.View):
    def __init__(self, nom_pos, we_are):
        super().__init__(timeout=None)
        self.nom_pos = nom_pos
        self.we_are = we_are
        self.format_self()

    def format_self(self):
        premove = data["nominations"][self.nom_pos]["premoves"].get(str(self.we_are.id), {"public": None, "private": None})[self.selected_visibility()]
        self.vote_button.style = discord.ButtonStyle.grey
        self.abstain_button.style = discord.ButtonStyle.grey
        self.vote_button.disabled = False
        self.abstain_button.disabled = False
        for opt in self.conditional_select.options:
            opt.default = premove and opt.value == premove["type"]
        for item in self.children:
            if isinstance(item, Subselector):
                self.remove_item(item)
        if is_to_vote(self.nom_pos, self.we_are):
            self.remove_item(self.select_visibility)
            self.remove_item(self.conditional_select)
        if not can_vote(self.we_are):
            return self.clear_items()
        if vote_complaint(self.we_are, self.nom_pos)[1]:
            self.vote_button.disabled = True
            self.conditional_select.disabled = True
        match premove:
            case {"type": "constant", "value": True}:
                self.vote_button.style = discord.ButtonStyle.blurple
            case {"type": "constant", "value": False}:
                self.abstain_button.style = discord.ButtonStyle.blurple
            case {"type": "actual" | "prospective", "from": n, "to": m}:
                def set_from(x):
                    premove["from"] = x
                    return rerender_nomination(self.nom_pos)
                def set_to(x):
                    premove["to"] = x
                    return rerender_nomination(self.nom_pos)
                l = len(players())
                self.add_item(NumericSelect(lambda x: f"at least {x}, and", set_from, n, 0, m))
                self.add_item(NumericSelect(lambda x: f"less than {x}", set_to, m, n+1, l+1))
            case {"type": "butler", "who": user_id}:
                def set_user(x):
                    premove["who"] = x
                    return rerender_nomination(self.nom_pos)
                self.add_item(PlayerSelect(set_user, self.we_are, user_id))
        if has_voted(self.nom_pos, self.we_are):
            for item in self.children:
                item.disabled = item is not self.select_visibility
        return self

    @discord.ui.select(options=[discord.SelectOption(label="Public premove", value="public", emoji="👩", default=True), discord.SelectOption(label="Private premove", value="private", emoji="🕵️")], row=0)
    async def select_visibility(self, interaction, select):
        for opt in select.options:
            opt.default = opt.value == select.values[0]
        await interaction.response.edit_message(view=self.format_self())

    def selected_visibility(self):
        return discord.utils.get(self.select_visibility.options, default=True).value

    def set_premove(self, premove):
        premove_table = data["nominations"][self.nom_pos]["premoves"]
        which = self.selected_visibility()
        o = premove_table.setdefault(str(self.we_are.id), {"public": None, "private": None})
        old = o[which]
        o[which] = premove
        if o == {"public": None, "private": None}:
            premove_table.pop(str(self.we_are.id))
        return old

    async def set_constant(self, value):
        premove = {"type": "constant", "value": value}
        old = self.set_premove(premove)
        if premove == old:
            self.set_premove(None)
        save()
        if is_to_vote(self.nom_pos, self.we_are):
            await step_through()
        else:
            await rerender_nomination(self.nom_pos)

    @discord.ui.button(label="Vote")
    async def vote_button(self, interaction, button):
        await self.set_constant(True)
        await interaction.response.defer()

    @discord.ui.button(label="Abstain")
    async def abstain_button(self, interaction, button):
        await self.set_constant(False)
        await interaction.response.defer()

    @discord.ui.select(
        options=[
            discord.SelectOption(label="If the vote count is", value="actual"),
            discord.SelectOption(label="If the prospective vote count is", value="prospective"),
            discord.SelectOption(label="If someone else votes", value="butler")
        ],
        placeholder="Make a conditional premove"
    )
    async def conditional_select(self, interaction, select):
        value = select.values[0]
        match value:
            case "actual":
                premove = {"type": "actual", "from": 0, "to": votes_necessary(self.nom_pos)}
            case "prospective":
                premove = {"type": "prospective", "from": 0, "to": votes_necessary(self.nom_pos)}
            case "butler":
                premove = {"type": "butler", "who": discord.utils.find(lambda x: x != self.we_are, players()).id}
        self.set_premove(premove)
        save()
        await rerender_nomination(self.nom_pos)
        await interaction.response.defer()

in_bulletin = commands.check(lambda ctx: bool(is_player(ctx.author)) and ctx.channel.name == "public-bulletin")
is_storyteller = commands.has_permissions(administrator=True)

@bot.command(aliases=["nom"])
@in_bulletin
async def nominate(ctx, target: discord.Member):
    if data["is_night"]:
        return await ctx.send("🥱")
    if not is_alive(ctx.author):
        return await ctx.send("You are dead.")
    if not is_player(target):
        return await ctx.send("They aren't playing.")

    target_name = target.global_name or target.name
    bully = bulletin()
    noms = data["nominations"]

    for i, nom in enumerate(noms):
        is_premove = not (i < data["current_nomination"] or is_current(i))
        nominator, nominee = get_nominers(nom)
        msg_link = bully.get_partial_message(nom["message"]).jump_url
        if nominator == ctx.author and nominee == target:
            if is_premove:
                return await ctx.send(f"You're already nominating {target_name} ({msg_link}).")
            else:
                return await ctx.send(f"You already nominated {target_name} ({msg_link})... are you feeling okay?")
        if nominator == ctx.author:
            if is_premove:
                return await ctx.send(f"You already premoved nominating {nominee.mention} ({msg_link}). You can cancel your premoved nomination with `+unnominate`.", allowed_mentions=NOT_USERS)
            else:
                return await ctx.send(f"You already nominated {nominee.mention} ({msg_link}).", allowed_mentions=NOT_USERS)
        if nominee == target:
            if is_premove:
                return await ctx.send(f"{target_name} is already being nominated by {nominator.mention} ({msg_link}).", allowed_mentions=NOT_USERS)
            else:
                return await ctx.send(f"{target_name} has already been nominated by {nominator.mention} ({msg_link}).", allowed_mentions=NOT_USERS)

    new_nom = {
        "nominator": ctx.author.id,
        "nominee": target.id,
        "premoves": {},
    }
    noms.append(new_nom)
    new_nom["message"] = (await ctx.send(embed=render_nomination(len(noms)-1, None), view=NominationView())).id

    save()

@bot.command(aliases=["unnom"])
@in_bulletin
async def unnominate(ctx):
    noms = data["nominations"]
    for i, nom in enumerate(noms):
        nominator, nominee = get_nominers(nom)
        if nominator == ctx.author:
            break
    else:
        return await ctx.send("You have no premoved nomination to cancel.")

    if i < data["current_nomination"] or is_current(i):
        return await ctx.send("You can only cancel premoved nominations; yours has already been performed.")

    noms.pop(i)
    await ctx.channel.get_partial_message(nom["message"]).edit(content=f"Nomination cancelled. ({ctx.message.jump_url})", embed=None, view=None)
    await ctx.message.add_reaction("👍")
    save()

async def step_through():
    current = data["current_nomination"]
    l = len(players())
    while data["to_vote"] < l:
        player = nomination_players(current)[data["to_vote"]]
        if not seen_premove(current, player, player):
            await bulletin().send(f"{player.mention} is next to vote.", delete_after=0)
            await rerender_nomination(current)
            save()
            break
        data["to_vote"] += 1
    else:
        await end_nomination()

@bot.command()
@is_storyteller
async def start(ctx):
    if data["to_vote"] is not None:
        return await ctx.send("A nomination is already running.")
    current = data["current_nomination"]
    if current == len(data["nominations"]):
        return await ctx.send("There is no premoved nomination to start.")

    current_nom = data["nominations"][current]
    nominator, nominee = get_nominers(current_nom)
    if not is_alive(nominator):
        return await ctx.send("The nominator is dead. Use +skip to ignore this premove.")

    msg_link = bulletin().get_partial_message(current_nom["message"]).jump_url
    await game_state().send(f"{nominee.mention} has been nominated ({msg_link}). <@&{PLAYER_ROLE_ID}> will have to vote.")

    data["to_vote"] = 0
    save()
    await step_through()
    await ctx.message.add_reaction("👍")

async def end_nomination():
    current = data["current_nomination"]
    data["current_nomination"] += 1
    data["to_vote"] = None
    votes = eval_votes(current)
    save()
    for voter in votes:
        if not is_alive(voter):
            await spend_vote(voter)
    nominator, nominee = get_nominers(data["nominations"][current])
    people = "people" if len(votes) != 1 else "person"
    msg = f"{nominee.global_name or nominee.name}'s nomination (by {nominator.mention}) has concluded. {len(votes)} {people} voted."
    if len(votes) > votes_necessary(current):
        msg += f" {nominee.global_name or nominee.name} is now about to die."
    await game_state().send(msg)
    await rerender_nomination(current)

@bot.command()
@is_storyteller
async def skip(ctx):
    await end_nomination()
    save()
    await ctx.message.add_reaction("👍")

@bot.command()
@is_storyteller
async def force(ctx, who: discord.Member, vote: bool, on_whom: discord.Member = None):
    if not is_player(who):
        return await ctx.send("They aren't even playing, man...")
    if not on_whom:
        nom_pos = data["current_nomination"] - (not data["to_vote"])
        if not 0 <= nom_pos < len(data["nominations"]):
            return await ctx.send("No running or previous nomination to force on. To force on a future nomination, pass the nominee's name as the third parameter.")
    else:
        for nom_pos, nom in enumerate(data["nominations"]):
            if nom["nominee"] == on_whom.id:
                break
        else:
            return await ctx.send(f"No nomination of {on_whom.global_name or on_whom.name} found.")

    data["nominations"][nom_pos]["premoves"][str(who.id)] = {"public": {"type": "constant", "value": vote}, "private": None}
    save()
    if is_to_vote(nom_pos, who):
        await step_through()
    else:
        await rerender_nomination(nom_pos)

@bot.command()
@is_storyteller
async def dawn(ctx):
    global data
    data = {"current_nomination": 0, "to_vote": None, "nominations": [], "is_night": False}
    save()
    await ctx.message.add_reaction("👍")

@bot.command()
@is_storyteller
async def dusk(ctx):
    while data["current_nomination"] < len(data["nominations"]):
        await end_nomination()
    data["is_night"] = True
    save()
    await ctx.message.add_reaction("👍")

async def setup_hook():
    await bot.load_extension("jishaku")
    bot.add_view(NominationView())

bot.setup_hook = setup_hook
bot.run(TOKEN)
