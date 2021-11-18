import asyncio
import importlib
from datetime import datetime
from typing import Union

import discord
from discord.ext import commands

import common.cards as cards
import common.fuzzys as fuzzys
import common.utils as utils


class CardHandling(commands.Cog, name="Card Handling"):
    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @commands.command()
    @commands.is_owner()
    async def update_card_data(self, ctx: commands.Context):
        importlib.reload(cards)

        extensions = [i for i in self.bot.extensions.keys()]
        for extension in extensions:
            self.bot.reload_extension(extension)

        await ctx.reply("Done!")

    @commands.command()
    @utils.proper_permissions()
    async def update_cast(self, ctx: commands.Context):

        async with ctx.typing():
            profile_chan: discord.TextChannel = self.bot.get_channel(675066875180351494)

            def is_valid(m: discord.Message):
                return m.author.id == self.bot.user.id

            reference_date = datetime(2021, 11, 17)
            await profile_chan.purge(limit=100, check=is_valid, after=reference_date)

            if cards.hosts:
                await profile_chan.send("```\nKG Hosts\n```")

                for host_card in cards.hosts:
                    embed = await host_card.as_embed(ctx.bot)
                    await profile_chan.send(embed=embed)
                    await asyncio.sleep(1)  # ratelimits

            await profile_chan.send("```\nParticipants\n```")

            for participant_card in cards.participants:
                embed = await participant_card.as_embed(ctx.bot)
                await profile_chan.send(embed=embed)
                await asyncio.sleep(1)

            embed = discord.Embed(timestamp=discord.utils.utcnow())
            embed.set_footer(text="Last Updated")

            await profile_chan.send(
                "All participant cards should be in alphabetical order and easily searchable.\n"
                + "If any information is wrong, ping or DM Astrea about it and she'll change it ASAP.\n"
                "If you want to get the individual, transparent image, you can also ping or DM Astrea for that too.",
                embed=embed,
            )

        await ctx.reply("Done!")

    @commands.command()
    async def search(
        self,
        ctx: commands.Context,
        *,
        query: Union[fuzzys.FuzzyOCNameConverter, fuzzys.FuzzyMemberConverter]
    ):
        """Allows to you to search and get a person's card based on the query provided.
        The query can either be the OC's name or their RPer's name.
        """

        # find all cards that have the same user id the person we got, and put those cards in a list in a list because
        # the exploit with FuzzyOCNameConverter that we might have to do requires that
        selected_cards = tuple(
            [c]
            for c in tuple(cards.participants + cards.hosts)
            if c.user_id == query.id
        )

        if not selected_cards:  # could be a member that doesn't have a card
            await ctx.reply("Invalid query!")
        else:
            if len(selected_cards) > 1:
                if not isinstance(query, (discord.User, discord.Member)):
                    # only would happen with oc name converter, which shouldnt be possible
                    # as there can be only one oc named something
                    raise utils.CustomCheckFailure(
                        "This shouldn't happen. Contact Astrea immediately - she has some debugging to do."
                    )

                # time to abuse the converter to do things
                oc_converter = fuzzys.FuzzyOCNameConverter()
                card = await oc_converter.selection_handler(ctx, selected_cards)
            else:
                card = selected_cards[0][0]

            embed = await card.as_embed(self.bot)
            await ctx.reply(embed=embed)


def setup(bot):
    importlib.reload(utils)
    importlib.reload(fuzzys)
    bot.add_cog(CardHandling(bot))
