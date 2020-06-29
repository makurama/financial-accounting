"""
module contains business logic for get report
:classes:
ReportService - сlass implements business logic get methods
ReportDataError - class exception with incorrect data
ReportCategoryError - class with the exception of a nonexistent entity
"""
from models import OperationModel, CategoryModel, LevelCategoryModel
from sqlalchemy import func, and_, orm, literal, alias, select, between
from services.category import CategoryService
from flask import jsonify
from entities.category import CategoryTree
from datetime import datetime, timezone, date, timedelta
import time
from dateutil.relativedelta import relativedelta
from src.ready_date import get_date
import calendar
from entities.report import ReportReturn
from src.exceptions import ServiceError


class ReportDataError(ServiceError):
    """
    class exception with incorrect data
    """
    service = 'report'


class ReportCategoryError(ReportDataError):
    """
    class with the exception of a nonexistent entity
    """
    message = {"answer": "Cущности не существует"}


class ReportService:
    """
    сlass implements business logic get methods
    """
    def __init__(self, session, user_id):
        """
        class constructor
        :param session: connect to db
        :param user_id: user id in session
        """
        self.session = session
        self.user_id = user_id

    def get_report(self, report):
        """
        generates a report on the specified parameters
        :param report: data for search
        :return: dataclass report
        """
        report.page = ((report.page - 1) * report.page_size)
        if report.category_name is not None:
            report.category_name = report.category_name.lower()

        query = (
            self.session.query(OperationModel)
                .filter(OperationModel.user_id == self.user_id)
                .order_by(OperationModel.datetime.desc())
           )

        if report.category_name is None:
            query = query.outerjoin(CategoryModel,
                                    OperationModel.category_id ==
                                    CategoryModel.id)
        else:
            query_category_id = (
                self.session.query(CategoryModel.id)
                .filter(and_(CategoryModel.name == report.category_name,
                             CategoryModel.user_id == self.user_id)).scalar()
            )
            if query_category_id is None:
                raise ReportCategoryError

            tree = self.__get_category_by_id(query_category_id)
            query = (
                query.join(CategoryModel,
                           OperationModel.category_id ==
                           CategoryModel.id)
                     .filter(CategoryModel.id.in_(tree))
            )

        if report.ready_date is not None:
            if report.ready_date == 'all_time':
                pass
            else:
                date_today = datetime.now()
                start_date, finish_date = get_date(date_today, report.ready_date)

                query = query.filter(between(OperationModel.datetime,
                                             start_date, finish_date))

        elif report.start_date is not None and report.finish_date is not None:
            query = query.filter(between(OperationModel.datetime,
                                         report.start_date,
                                         report.finish_date))

        query = query.limit(report.page_size).offset(report.page).all()

        query_list = []

        for record in query:
            query_list.append(record.as_dict())

        id_sum_list = []
        for item in query_list:
            if item.get('category_id') is not None:
                item.update({"category": self.__get_up_category_tree(
                    item.get('category_id'))})

            id_sum_list.append(item.get('id'))
            item.update({'amount': item.get('amount')/100})
            del item['id']
            del item['type_operation']
            del item['user_id']
            del item['category_id']

        #TODO не забыть добавить
        result_sum = ((
            self.session.query(func.sum(OperationModel.amount))
                .filter(and_(OperationModel.id.in_(id_sum_list),
                             OperationModel.type_operation == 'consumption'))).scalar())

        if result_sum is not None:
            result_sum = result_sum / 100

        return jsonify(query_list)

    def __get_category_by_id(self, category_id):
        """
        builds a category tree
        :param category_id: id parent category
        :return: list category tree
        """
        tree = []
        children = (
            self.session.query(LevelCategoryModel)
                .filter(LevelCategoryModel.parent_id == category_id).all())
        tree.append(category_id)
        for child in children:
            a = self.__get_category_by_id(child.children_id)
            tree.extend(a)
        return tree

    def __get_up_category_tree(self, category_id):
        """
        rises up the category tree
        :param category_id: id children category
        :return: list parent category
        """
        category_list = []
        while True:
            category = (
                self.session.query(LevelCategoryModel)
                    .filter(LevelCategoryModel.children_id == category_id)
            )
            category = category.join(CategoryModel,
                                     CategoryModel.id ==
                                     LevelCategoryModel.children_id).first()

            category_id = category.as_dict().get('parent_id')

            if category.as_dict().get('parent_id') is None:
                category_list.append(self.session.query(CategoryModel).filter(
                    CategoryModel.id == category.as_dict().get('children_id')).first())
                break

            category_list.append(self.session.query(CategoryModel).filter(
                CategoryModel.id == category.as_dict().get('children_id')).first())

        return_category_list = []
        for item in category_list:
            item = item.as_dict()
            del item['user_id']
            return_category_list.append(item)

        return return_category_list
