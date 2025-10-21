import re
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

class Live(commands.Cog):
    """Tools for livetext."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author) or ctx.guild and any(role.name == "Storytellers" for role in ctx.author.roles)

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
        role = discord.utils.get(ctx.guild.roles, name="Players")
        alive = discord.utils.get(ctx.guild.roles, name="Alive")
        for i, player in enumerate(players, start=1):
            try:
                await player.edit(nick=f"[{i}] {re.sub(r"^\[\d+\] ", "", player.display_name)}")
            except discord.Forbidden:
                pass
            await player.add_roles(role, alive)

    @commands.command()
    async def construct(self, ctx, *people: discord.Member):
        storytellers = discord.utils.get(ctx.guild.roles, name="Storytellers")
        meeting_bot = discord.utils.get(ctx.guild.roles, name="Meeting Bot")
        players = discord.utils.get(ctx.guild.roles, name="Players")

        category = await ctx.guild.create_category(name="In game", position=0)

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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.message_id == 1419689462413398158:
            member = payload.member
            await    member.add_roles(discord.utils.get(member.guild.roles, name="Queue Ping"))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.message_id == 1419689462413398158:
            member = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
            await member.remove_roles(discord.utils.get(member.guild.roles, name="Queue Ping"))


async def setup(bot):
    await bot.add_cog(Live(bot))
