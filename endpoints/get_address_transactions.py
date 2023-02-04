# encoding: utf-8
from typing import List

from fastapi import Path, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.future import select
from endpoints.get_transactions import search_for_transactions, TxSearch, TxModel

from dbsession import async_session
from server import app

from models.TxAddrMapping import TxAddrMapping

class TransactionsReceivedAndSpent(BaseModel):
    tx_received: str
    tx_spent: str | None
    # received_amount: int = 38240000000


class TransactionForAddressResponse(BaseModel):
    transactions: List[TransactionsReceivedAndSpent]


@app.get("/addresses/{kaspaAddress}/transactions",
         response_model=TransactionForAddressResponse,
         response_model_exclude_unset=True,
         tags=["Kaspa addresses"])
async def get_transactions_for_address(
        kaspaAddress: str = Path(
            description="Kaspa address as string e.g. "
                        "kaspa:pzhh76qc82wzduvsrd9xh4zde9qhp0xc8rl7qu2mvl2e42uvdqt75zrcgpm00",
            regex="^kaspa\:[a-z0-9]{61}$")):
    """
    Get all transactions for a given address from database
    """
    # SELECT transactions_outputs.transaction_id, transactions_inputs.transaction_id as inp_transaction FROM transactions_outputs
    #
    # LEFT JOIN transactions_inputs ON transactions_inputs.previous_outpoint_hash = transactions_outputs.transaction_id AND transactions_inputs.previous_outpoint_index::int = transactions_outputs.index
    #
    # WHERE "script_public_key_address" = 'kaspa:qp7d7rzrj34s2k3qlxmguuerfh2qmjafc399lj6606fc7s69l84h7mrj49hu6'
    #
    # ORDER by transactions_outputs.transaction_id
    async with async_session() as session:
        resp = await session.execute(text(f"""
            SELECT transactions_outputs.transaction_id, transactions_outputs.index, transactions_inputs.transaction_id as inp_transaction,
                    transactions.block_time, transactions.transaction_id
            
            FROM transactions
			LEFT JOIN transactions_outputs ON transactions.transaction_id = transactions_outputs.transaction_id
			LEFT JOIN transactions_inputs ON transactions_inputs.previous_outpoint_hash = transactions.transaction_id AND transactions_inputs.previous_outpoint_index::int = transactions_outputs.index
            WHERE "script_public_key_address" = '{kaspaAddress}'
			ORDER by transactions.block_time DESC
			LIMIT 500"""))

        resp = resp.all()

    # build response
    tx_list = []
    for x in resp:
        tx_list.append({"tx_received": x[0],
                        "tx_spent": x[2]})
    return {
        "transactions": tx_list
    }

@app.get("/addresses/{kaspaAddress}/transactions/v2",
         response_model=List[TxModel],
         response_model_exclude_unset=True,
         tags=["Kaspa addresses transactions"])
async def get_transactions_for_address_v2(
        kaspaAddress: str = Path(
            description="Kaspa address as string e.g. "
                        "kaspa:pzhh76qc82wzduvsrd9xh4zde9qhp0xc8rl7qu2mvl2e42uvdqt75zrcgpm00",
            regex="^kaspa\:[a-z0-9]{61}$"),
        limit: int = Query(
            description="The number of records to get",
            ge=1,
            le=500,
            default=50),
        offset: int = Query(
            description="The offset from which to get records",
            ge=0,
            default=0),
        fields: str = "",
    ):
    """
    Get all transactions for a given address from database.
    And then get their related full transactiond data
    """

    async with async_session() as s:
        # Doing it this way as opposed to adding it directly in the IN clause
        # so I can re-use the same result in tx_list, TxInput and TxOutput
        txWithinLimitOffset = await s.execute(select(TxAddrMapping.transaction_id)
            .filter(TxAddrMapping.address == kaspaAddress)
            .limit(limit)
            .offset(offset)
            .order_by(TxAddrMapping.block_time.desc())
        )

        txIdsInPage = [x[0] for x in txWithinLimitOffset.all()]

    return await search_for_transactions(TxSearch(transactionIds=txIdsInPage), fields)
