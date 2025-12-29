import base64
import io
import re

import nh3
import parse_discord
import discord
from discord.ext import commands


STORYTELLER = discord.PermissionOverwrite(
    send_messages=True,
    send_messages_in_threads=True,
    create_public_threads=True,
    create_private_threads=True,
    manage_messages=True,
    manage_threads=True,
    add_reactions=True,
)
CAN_SPEAK = discord.PermissionOverwrite(
    send_messages=True,
    send_messages_in_threads=True,
    add_reactions=True,
)
CANNOT_SPEAK = discord.PermissionOverwrite(
    send_messages=False,
    send_messages_in_threads=False,
    create_public_threads=False,
    create_private_threads=False,
    add_reactions=False,
)

with open("main.css") as f, open("main.js") as g:
    CSS = f.read()
    JS = g.read()


def serialize_content(markup, guild):
    out = []
    for node in markup.nodes:
        match node:
            case parse_discord.Text(t):
                out.append(nh3.clean(t))
            case parse_discord.Bold(inner):
                out.append('<b>')
                out.append(serialize_content(inner, guild))
                out.append('</b>')
            case parse_discord.Italic(inner):
                out.append('<i>')
                out.append(serialize_content(inner, guild))
                out.append('</i>')
            case parse_discord.Underline(inner):
                out.append('<u>')
                out.append(serialize_content(inner, guild))
                out.append('</u>')
            case parse_discord.Strikethrough(inner):
                out.append('<s>')
                out.append(serialize_content(inner, guild))
                out.append('</s>')
            case parse_discord.Spoiler(inner):
                out.append('<span class="spoiler"><span>')
                out.append(serialize_content(inner, guild))
                out.append('</span></span>')
            case parse_discord.Quote(inner):
                out.append('<blockquote>')
                out.append(serialize_content(inner, guild))
                out.append('</blockquote>')
            case parse_discord.Header(inner, level):
                out.append(f'<h{level}>')
                out.append(serialize_content(inner, guild))
                out.append(f'</h{level}>')
            case parse_discord.Subtext(inner):
                out.append(f'<sub>')
                out.append(serialize_content(inner, guild))
                out.append(f'</sub>')
            case parse_discord.List(start, items):
                out.append('<ul>' if start is None else f'<ol start="{start}">')
                for item in items:
                    out.append('<li>')
                    out.append(serialize_content(item, guild))
                    out.append('</li>')
                out.append('</ul>' if start is None else '</ol>')
            case parse_discord.Link(appearance=appearance, target=target):
                out.append(f'<a href="{target}">')
                out.append(serialize_content(appearance, guild))
                out.append('</a>')
            case parse_discord.InlineCode(content):
                out.append('<code>')
                out.append(content)
                out.append('</code>')
            case parse_discord.Codeblock(language, content):
                out.append('<pre><code>' if language is None else f'<pre><code class="language-{language}">')
                out.append(content)
                out.append('</code></pre>')
            case parse_discord.UserMention(id):
                member = guild.get_member(id)
                name = member.display_name if member else "[unknown user]"
                out.append(f'<span class="mention user" data-id="{id}">@{name}</span>')
            case parse_discord.ChannelMention(id):
                channel = guild.get_channel(id)
                name = channel.name if channel else "[unknown channel]"
                out.append(f'<span class="mention">#{name}</span>')
            case parse_discord.RoleMention(id):
                role = guild.get_role(id)
                name = role.name if role else "[unknown role]"
                out.append(f'<span class="mention">@{name}</span>')
            case parse_discord.Everyone():
                out.append('<span class="mention">@everyone</span>')
            case parse_discord.Here():
                out.append('<span class="mention">@here</span>')
            case parse_discord.CustomEmoji(id, name):
                out.append(f'<img class="emoji" src="https://cdn.discordapp.com/emojis/{id}.webp?size=56" alt=":{name}:" draggable="false">')
            case parse_discord.UnicodeEmoji(char):
                out.append(char)
            case parse_discord.Timestamp(format=format):
                if format not in ("t", "T", "d", "D", "f", "F", "s", "S", "R"):
                    format = "f"
                datetime = node.as_datetime().isoformat()
                out.append(f'<time datetime="{datetime}" data-format="{format}">{datetime}</time>')
    return "".join(out)


class Live(commands.Cog):
    """Tools for livetext."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author) or ctx.guild and any(role.name == "Storytellers" for role in ctx.author.roles)

    @commands.command()
    @commands.is_owner()
    async def log(self, ctx, category: discord.CategoryChannel):
        name = category.name.removesuffix("(Archive)").strip()
        sidebar = []
        tabs = []

        threads = [
            thread for channel in category.text_channels for thread in [
                channel,
                *channel.threads,
                *[thread async for thread in channel.archived_threads(limit=None)],
                *[thread async for thread in channel.archived_threads(limit=None, private=True)],
            ]
        ]

        for thread in threads:
            symbol = "#" if thread.type == discord.ChannelType.text else "↪ "
            sidebar.append(f"<a>{symbol}{thread.name}</a>")

            messages = []
            async for message in thread.history(limit=None, oldest_first=True):
                content = message.content if message.type != discord.MessageType.thread_starter_message else message.reference.resolved.content
                content_part = serialize_content(parse_discord.parse(message.content), category.guild)

                attachments = []
                for attachment in message.attachments:
                    if attachment.size >= 2_000_000 or not attachment.content_type.startswith("image"):
                        continue
                    # why are there so many useful operations this library just doesn't support
                    attachment.proxy_url += "&format=webp"
                    data = await attachment.read(use_cached=True)
                    alt = f' alt="{attachment.description}"' if attachment.description else ""
                    url = f"data:{attachment.content_type};base64,{base64.b64encode(data).decode()}"
                    attachments.append(f'<img{alt} class="a" src="{url}">')
                for sticker in message.stickers:
                    if sticker.format == discord.StickerFormatType.lottie:
                        continue
                    attachments.append(f'<img class="a sticker" alt="{sticker.name}" src="{sticker.url}">')
                if message.thread:
                    attachments.append(f'<a class="a goto" data-goto="{threads.index(message.thread)}" href="javascript:void(0)">{message.thread.name}</a>')
                if message.poll:
                    answers = []
                    for answer in message.poll.answers:
                        answers.append(f'<span class="poll-a">{answer.text}</span> <span class="poll-c">({answer.vote_count})</span><ul>')
                        async for voter in answer.voters():
                            answers.append(f'<li class="user" data-id="{voter.id}">{voter.display_name}</li>')
                        answers.append("</ul>")
                    attachments.append(f'<div class="a poll"><h4>{message.poll.question}</h4>{"".join(answers)}</div>')

                if not content_part and not attachments:
                    # we have no idea how to show this message and it's probably not that important. just skip it
                    continue

                messages.append(
                    f'<div class="message" data-id="{message.id}"><span class="name user" data-id="{message.author.id}">{message.author.display_name}</span>'
                    f' <span class="c">{content_part}</span>{"".join(attachments)}</div>'
                )

            tabs.append(f'<div class="content">{"".join(messages)}</div>')

        page = (
            '\n\n\n\n\n<!-- download and open file to view log -->\n'
            f'<!DOCTYPE html><html><head><title>{name} - Gallows Guild: BotC</title><style>{CSS}</style><script defer>{JS}</script></head><body><div id="sidebar">{"".join(sidebar)}</div>{"".join(tabs)}</body></html>'
        ).encode()
        filename = f"{category.created_at.strftime('%Y-%m-%d-%H-%M')}-{name.replace('/', '')}.html"
        with open(f"logs/{filename}", "wb") as f:
            f.write(page)
        # try:
        #     await ctx.send(file=discord.File(io.BytesIO(page), filename=filename))
        # except discord.HTTPException:
        #     await ctx.send("Log too large to send, but it has been saved.")

    @commands.command()
    async def archive(self, ctx, category: discord.CategoryChannel, *, game_name):
        await category.edit(
            name=f"{game_name} (Archive)",
            overwrites={
                ctx.guild.default_role: CANNOT_SPEAK,
            },
        )
        for channel in category.text_channels:
            await channel.edit(sync_permissions=True)
        await ctx.message.add_reaction("👍")

    async def the_players_are(self, ctx, players):
        for player in players:
            if any(role.name == "Game Suspension" for role in player.roles):
                await ctx.send(f"{player.name} is suspended.")

        role = discord.utils.get(ctx.guild.roles, name="Players")
        alive = discord.utils.get(ctx.guild.roles, name="Alive")
        for i, player in enumerate(players, start=1):
            new_name = f"[{i}] {re.sub(r"^\[\d+\] ", "", player.display_name[max(len(player.display_name) + 5 - 32, 0):])}"
            try:
                await player.edit(nick=new_name)
            except discord.Forbidden:
                pass
            await player.add_roles(role, alive)

    @commands.command()
    async def construct(self, ctx, *people: discord.Member):
        storytellers = discord.utils.get(ctx.guild.roles, name="Storytellers")
        meeting_bot = discord.utils.get(ctx.guild.roles, name="Meeting Bot")
        players = discord.utils.get(ctx.guild.roles, name="Players")

        category = await ctx.guild.create_category(name="In game")
        await category.move(beginning=True, offset=1)

        top_2 = {
            storytellers: STORYTELLER,
            ctx.guild.default_role: CANNOT_SPEAK,
        }
        bottom_2 = {
            storytellers: STORYTELLER,
            meeting_bot: STORYTELLER,
            players: CAN_SPEAK,
            ctx.guild.default_role: CANNOT_SPEAK,
        }

        await category.create_text_channel("rules", overwrites=top_2)
        await category.create_text_channel("game-state", overwrites=top_2)
        await category.create_text_channel("public-bulletin", overwrites=bottom_2)
        await category.create_text_channel("town-square", overwrites=bottom_2)
        await category.create_text_channel("peanut-gallery", overwrites={players: discord.PermissionOverwrite(view_channel=False)})

        await self.the_players_are(ctx, people)
        await ctx.message.add_reaction("👍")

    @commands.command()
    async def players(self, ctx, *people: discord.Member):
        await self.the_players_are(ctx, people)
        await ctx.message.add_reaction("👍")

    @commands.command()
    async def gg(self, ctx):
        players = discord.utils.get(ctx.guild.roles, name="Players")
        alive = discord.utils.get(ctx.guild.roles, name="Alive")
        dead_vote = discord.utils.get(ctx.guild.roles, name="Dead (can vote)")
        dead_no_vote = discord.utils.get(ctx.guild.roles, name="Dead (can't vote)")
        for member in ctx.guild.members:
            if players in member.roles:
                await member.remove_roles(players, alive, dead_vote, dead_no_vote)
            if member.nick is not None and (new_nick := re.sub(r"^\[\d+\] ", "", member.nick)) != member.nick:
                try:
                    await member.edit(nick=new_nick)
                except discord.Forbidden:
                    pass
        await ctx.message.add_reaction("👍")

    @commands.command(aliases=["deconstruct"])
    async def destruct(self, ctx, category: discord.CategoryChannel):
        for channel in category.channels:
            await channel.delete()
        await category.delete()
        await ctx.message.add_reaction("👍")

    @staticmethod
    def which_role(payload, roles):
        return discord.utils.get(roles, name="Jackbox Ping") if payload.emoji.name == "📦" else discord.utils.get(roles, name="Queue Ping")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.message_id == 1419689462413398158:
            member = payload.member
            await member.add_roles(self.which_role(payload, member.guild.roles))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.message_id == 1419689462413398158:
            member = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
            await member.remove_roles(self.which_role(payload, member.guild.roles))


async def setup(bot):
    await bot.add_cog(Live(bot))
