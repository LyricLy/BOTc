import datetime
import random

import discord
from discord.ext import commands

import config


def message_embed(message):
    embed = discord.Embed(description=message.content)
    embed.set_footer(text="#" + message.channel.name)
    embed.timestamp = message.edited_at or message.created_at
    embed.set_author(name=message.author.global_name or message.author.name, icon_url=message.author.display_avatar)
    if message.attachments:
        attachment = message.attachments[0]
        if attachment.filename.endswith((".png", ".jpg", ".jpeg")):
            embed.set_image(url=attachment.url)
    return embed


class Fun(commands.Cog):
    """Miscellaneous games for GGBotC."""

    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx):
        return ctx.guild and ctx.guild.id == config.FUN_GUILD_ID

    async def pick_random_message(self, channel):
        t = channel.created_at + (datetime.datetime.now(datetime.timezone.utc) - channel.created_at) * random.random()
        ms = [m async for m in channel.history(around=t)]
        random.shuffle(ms)
        for message in ms:
            if not message.webhook_id and message.content and message.content.count(" ") > 3 and message.author in message.guild.members:
                break

        return message

    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command()
    async def hwdyk(self, ctx):
        """Pick a random message. If you can guess who sent it, you win!"""

        channel = self.bot.get_channel(config.HWDYK_CHANNEL_ID)
        special_channel = self.bot.get_channel(config.HWDYK_SPECIAL_CHANNEL_ID)
        message = await self.pick_random_message(channel if getattr(ctx.channel, "parent", ctx.channel) != special_channel or random.random() > 0.05 else special_channel)
        real_embed = message_embed(message)
        hidden_embed = real_embed.copy()
        hidden_embed.set_footer(text="#??? • ??/??/????")
        hidden_embed.set_author(name="❓  ???")
        hidden_embed.timestamp = None
        bot_msg = await ctx.reply("Who sent this message?", embed=hidden_embed)

        while True:
            r = await self.bot.wait_for("message", check=lambda m: m.channel == ctx.channel and m.author == ctx.author and not m.content.startswith("!"))
            try:
                member = await commands.MemberConverter().convert(ctx, r.content)
            except commands.BadArgument:
                pass
            else:
                break

        # reveal info
        await bot_msg.edit(embed=real_embed)

        if member == message.author:
            await r.reply("You were correct!")
        else:
            await r.reply("Too bad. Good luck with the next time!")


async def setup(bot):
    await bot.add_cog(Fun(bot))
